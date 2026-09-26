# Contributing to Spartina Earth

Thanks for your interest. This is a long-term research repository with
strict evidence rules — please read
[`AGENTS.md`](AGENTS.md) before opening a pull request.

## Ground rules

- **No fabricated results, paths, citations, or GEE assets.** Missing
  information is written as `UNKNOWN` / `MISSING` / `TODO_VERIFY`.
- **Legacy numbers stay unverified** until independently reproduced.
- **No large files** (imagery, arrays, checkpoints, archives) in Git. Use
  manifests to describe data; store bytes elsewhere.
- **No secrets** in commits (tokens, service-account JSON, keys).
- **Spatially disjoint splits only**; random neighboring-patch splits are
  rejected.
- Research claims and experiments must close: problem → method →
  experiment → metric.

## Development setup (M0, lightweight)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

M0 package runtime dependencies are intentionally zero (standard library
only). Do not add heavy geospatial/ML dependencies in M0; they are reserved
as optional extras for M1+.

## Branch model

- `main` — stable, protected; no force-pushes, no history rewrites.
- `reboot/spartina-earth-m0` — the M0 reboot branch.
- Later work: topic branches such as `feat/data-engine-grid`,
  `fix/...`, `docs/...`.

## Commit hygiene

- Small, logically scoped commits; no single giant commit.
- Use conventional prefixes: `feat:`, `fix:`, `docs:`, `test:`,
  `chore:`, `refactor:`.
- Run relevant tests before committing; `pre-commit` enforces formatting
  and the 1 MiB size limit.
- Never rewrite shared history or force-push to `main`.

## Pull requests

1. Link the issue / milestone (M0–M7).
2. State what changed and what evidence supports it.
3. New experiments must include config, manifest versions, seed, and
   results summary per
   [`docs/experiments/EXPERIMENT_STANDARD.md`](docs/experiments/EXPERIMENT_STANDARD.md).
4. New datasets require a manifest entry and a confirmed license.
5. CI must pass (ruff, mypy, pytest).

## Agent contributions

Agents are bound by [`AGENTS.md`](AGENTS.md). In particular: do not start
bulk GEE exports, foundation-model downloads, or multi-GPU training
without explicit user authorization; do not mark hypotheses as results.

## Conduct

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
