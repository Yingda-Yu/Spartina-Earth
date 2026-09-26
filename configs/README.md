# configs/

Versioned, human-reviewed configuration for data preparation, models,
training, evaluation, and experiment composition.

- `data/` — catalog queries, preprocessing, grid/QA settings (M1+)
- `model/` — architecture definitions (M3+)
- `train/` — optimizer/schedule/seed/resource settings (M3+)
- `eval/` — metric and evaluation-protocol settings (M2+)
- `experiment/` — composed experiment configs referencing the above

Rules:

- Configs are the *checked-in* part of reproducibility; the resolved
  effective config is also copied into every `runs/<run_id>/`.
- Prefer CLI parameters for per-run variation; never hard-code local data
  paths into shared configs.
- No credentials in configs.
