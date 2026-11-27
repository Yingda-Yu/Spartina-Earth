# datasets/

Only **manifests** are tracked in Git:

- `manifests/schema.json` — asset manifest schema (JSON Schema 2020-12)
- `manifests/*.json` — per-asset records (added from M1 onward)

Raw and processed bytes stay outside Git (`datasets/raw/`,
`datasets/processed/`, `datasets/external/` are git-ignored) and are
described exclusively through manifest records with checksums and
provenance chains. See
[`../docs/audit/DATA_INVENTORY.md`](../docs/audit/DATA_INVENTORY.md),
[`../docs/audit/LABEL_INVENTORY.md`](../docs/audit/LABEL_INVENTORY.md), and
[`../DATA_LICENSE.md`](../DATA_LICENSE.md).

Incoming legacy/transferred material lives at the workspace-local
`old datasets/` directory (git-ignored) until audited; it is not copied
here automatically.
