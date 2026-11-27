# tests/

- `smoke/` — minimal import / environment checks (must always pass
  offline).
- `unit/` — fast, hermetic, network-free tests (GEE interfaces tested with
  mocks here).
- `integration/` — tests requiring real external services; the GEE suite is
  marked `gee_integration`, auto-skips without credentials, and is
  deselected by default. Run with `pytest -m gee_integration` only when
  credentials exist, and keep it to tiny smoke queries.

Run everything M0-safe:

```bash
pytest                 # smoke + unit, no network
pytest -m "not gee_integration"
```
