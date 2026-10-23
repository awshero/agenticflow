"""Lifecycle_APC: decides whether an APC is in steady use, still being tuned,
dormant or gone - from its configuration-change history.

Data scientists flip APC configs as projects evolve (bigger driver for a
training run, back to the usual shape afterwards). Collapsing the history into
spans of identical configuration and counting how often each configuration
comes back separates three situations:

* a *repeating* config (seen in >= N separate spans) is a known-good shape the
  owner keeps returning to - safe to optimise;
* a young, never-seen-before config on a churning cluster means the owner is
  still experimenting - recommendations are held back (EXPERIMENTAL);
* no runtime in the active window means DORMANT regardless of config.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence

from apc_optimizer.config import EngineConfig
from apc_optimizer.models import (
    ClusterMetrics,
    ConfigSnapshot,
    LifecycleAssessment,
    LifecycleState,
)


@dataclass
class ConfigSpan:
    fingerprint: str
    start: datetime
    end: datetime

    @property
    def days(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds() / 86400.0)


def _naive(ts: Optional[datetime]) -> Optional[datetime]:
    return ts.replace(tzinfo=None) if ts is not None and ts.tzinfo else ts


def _as_of(metrics: ClusterMetrics, as_of: Optional[datetime]) -> datetime:
    if as_of is not None:
        return _naive(as_of)
    if isinstance(metrics.snapshot_date, date):
        return datetime.combine(metrics.snapshot_date, datetime.min.time())
    return datetime.utcnow()


def build_spans(history: Sequence[ConfigSnapshot], as_of: datetime) -> List[ConfigSpan]:
    """Collapse change rows into spans of identical configuration.

    system.compute.clusters writes a row for any edit (tags, name, ...), so
    consecutive rows with the same fingerprint are merged into one span.
    """
    rows = sorted(history, key=lambda r: _naive(r.change_time))
    spans: List[ConfigSpan] = []
    for row in rows:
        ts = _naive(row.change_time)
        fp = row.fingerprint()
        if spans and spans[-1].fingerprint == fp:
            continue
        if spans:
            spans[-1].end = ts
        spans.append(ConfigSpan(fingerprint=fp, start=ts, end=as_of))
    return spans


class LifecycleAPC:
    def __init__(self, config: EngineConfig):
        self.cfg = config

    def assess(
        self,
        metrics: ClusterMetrics,
        history: Sequence[ConfigSnapshot],
        as_of: Optional[datetime] = None,
    ) -> LifecycleAssessment:
        now = _as_of(metrics, as_of)
        lookback = int(self.cfg.get("global.lookback_days", 30))
        active_window = int(self.cfg.get("global.active_window_days", 14))
        max_changes = int(self.cfg.get("lifecycle.max_config_changes", 6))
        min_stable_days = float(self.cfg.get("lifecycle.min_stable_days", 7))
        min_occ = int(self.cfg.get("lifecycle.recurring_min_occurrences", 2))
        window_start = now - timedelta(days=lookback)

        spans = build_spans(history, now)
        occurrences = Counter(s.fingerprint for s in spans)
        repeating = sorted(fp for fp, n in occurrences.items() if n >= min_occ)

        time_share: Dict[str, float] = defaultdict(float)
        for s in spans:
            lo, hi = max(s.start, window_start), min(s.end, now)
            if hi > lo:
                time_share[s.fingerprint] += (hi - lo).total_seconds()
        total = sum(time_share.values())
        dominant, dominant_share = None, 0.0
        if total > 0:
            dominant = max(time_share, key=time_share.get)
            dominant_share = time_share[dominant] / total

        changes = sum(1 for s in spans[1:] if s.start >= window_start)
        current = spans[-1] if spans else None
        if current is not None:
            age_days: Optional[float] = current.days
        elif metrics.last_config_change_time is not None:
            age_days = (now - _naive(metrics.last_config_change_time)).total_seconds() / 86400.0
        else:
            age_days = None
        current_repeating = current is not None and current.fingerprint in repeating

        deleted = metrics.delete_time is not None or any(h.delete_time for h in history)
        last_active = _naive(metrics.last_active_time)
        recently_used = (
            metrics.uptime_minutes > 0
            and last_active is not None
            and last_active >= now - timedelta(days=active_window)
        )

        if deleted:
            state, reason = LifecycleState.DELETED, "cluster deleted"
        elif not recently_used:
            state = LifecycleState.DORMANT
            reason = f"no activity in the last {active_window} days"
        elif (
            changes > max_changes
            and not current_repeating
            and (age_days is not None and age_days < min_stable_days)
        ):
            state = LifecycleState.EXPERIMENTAL
            reason = (
                f"{changes} config changes in {lookback}d and current config is new "
                f"({age_days:.1f}d) and not a repeating config"
            )
        else:
            state = LifecycleState.ACTIVE
            if current_repeating:
                reason = "in use on a repeating configuration"
            else:
                reason = "in use on a stable configuration"

        stability = self._stability(state, changes, age_days, current_repeating, min_stable_days)
        return LifecycleAssessment(
            state=state,
            config_change_count=changes,
            distinct_config_count=len(occurrences),
            repeating_configs=repeating,
            current_config_age_days=age_days,
            current_config_is_repeating=current_repeating,
            dominant_config=dominant,
            dominant_config_share=round(dominant_share, 4),
            stability=stability,
            reason=reason,
        )

    @staticmethod
    def _stability(
        state: LifecycleState,
        changes: int,
        age_days: Optional[float],
        repeating: bool,
        min_stable_days: float,
    ) -> float:
        if state is not LifecycleState.ACTIVE:
            return 0.3
        if repeating or (age_days is not None and age_days >= 2 * min_stable_days):
            base = 1.0
        elif age_days is None:
            base = 0.8
        elif age_days >= min_stable_days:
            base = 0.85
        else:
            base = 0.6
        return round(max(0.0, base - min(0.3, 0.03 * changes)), 4)
