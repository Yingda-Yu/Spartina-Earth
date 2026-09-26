# scripts/

Operational scripts (thin wrappers over `src/spartina/`).

- `system/` — host probes and environment checks (see
  [`system/probe.py`](system/probe.py))
- `data/` — catalog/export/QA/tiling operations (M1+)
- `train/` — training entry points (M3+)
- `eval/` — evaluation and benchmark scoring (M2+)
- `audit/` — one-off audit/inventory helpers

Scripts must be safe by default: read-only audits never modify data;
anything that exports, downloads, or trains requires explicit flags and
prints what it will do before doing it.
