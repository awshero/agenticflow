---
name: system-design
description: Runs the full stack system design pipeline - architect, API, database, frontend, infrastructure, then an adversarial review with a fix loop - and produces a linked design doc set in docs/design/. Use when someone asks to design a system, app, backend, service, or feature end to end, or says "system design". For one layer only, such as just the API or just the schema, use that designer agent directly instead.
---

# System design pipeline

Design this: $ARGUMENTS

If nothing was given, ask what to design. Pick a short kebab-case `<slug>` and tell each agent to write to `docs/design/<slug>/`.

Run the agents from this main session, because each step needs the previous step's files. Pass each one the slug, the request, and any answers the user has given. They read the earlier documents themselves, so do not paste them in.

## Steps

1. **`system-architect`** — writes the brief. Then stop and show the user the assumptions and top decisions, and get confirmation before continuing, because everything downstream depends on them. Skip this stop only if the user asked for an unattended run.
2. **`api-designer`** — needs the brief.
3. **`db-designer`** — needs the API's access patterns.
4. **`frontend-designer`** and **`infra-designer`** — run in parallel. Skip the frontend if the user said there is no client.
5. **Apply change requests.** If the DB or frontend designer asked for API changes, send them back to `api-designer`, then to `db-designer` if the schema is affected.
6. **`design-reviewer`** — writes `06-review.md`.
7. **Fix loop.** Send each `BLOCKER` and `MAJOR` finding to its owning designer, then run `design-reviewer` again. Stop after two rounds, and report whatever is still open rather than looping further.

If an agent reports something it could not satisfy, or two agents disagree on a requirement, ask the user instead of choosing silently.

## Finish

Write `docs/design/<slug>/README.md`: a one-paragraph summary, links to each document, the decisions needing human attention, the assumptions, the review verdict, and any open findings.

Tell the user the verdict, the decisions they should check, and what is still open. Nothing has been built or run against real systems; these are design documents only.
