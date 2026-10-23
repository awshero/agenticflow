"""Instance catalog: node shapes, relative price and DBU rate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class InstanceType:
    name: str
    vcpu: int
    memory_gb: float
    price_per_hour: float
    dbu_per_hour: float

    @property
    def family(self) -> str:
        return self.name.split(".", 1)[0]

    def hourly_cost(self, dbu_rate: float) -> float:
        """Infra + DBU list cost per node-hour (used only for ranking/ratios)."""
        return self.price_per_hour + self.dbu_per_hour * dbu_rate


class InstanceCatalog:
    def __init__(self, raw: Dict[str, Dict[str, float]]):
        self._types = {
            name: InstanceType(
                name=name,
                vcpu=int(spec["vcpu"]),
                memory_gb=float(spec["memory_gb"]),
                price_per_hour=float(spec["price_per_hour"]),
                dbu_per_hour=float(spec["dbu_per_hour"]),
            )
            for name, spec in raw.items()
        }

    def get(self, name: Optional[str]) -> Optional[InstanceType]:
        return self._types.get(name) if name else None

    def candidates(
        self,
        current: InstanceType,
        allowed_families: Iterable[str],
        allow_family_change: bool,
    ) -> List[InstanceType]:
        allowed = set(allowed_families)
        out = []
        for t in self._types.values():
            if t.family not in allowed:
                continue
            if not allow_family_change and t.family != current.family:
                continue
            out.append(t)
        return out
