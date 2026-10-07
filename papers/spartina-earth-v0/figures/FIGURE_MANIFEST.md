# Figure Manifest — Spartina Earth v0

Per the academic-writing skill's rendering gate, this manifest is a
required deliverable while figures are placeholders. The manuscript
compiles labeled placeholder boxes only; no final artwork (TikZ, image,
`\includegraphics`) is rendered without an explicit per-figure request.
Reference/reference figures must be sourced from the same task domain
and hand-adapted; a single AI-generation pass is not an approved design.

## Fig. 1 — Spartina Earth scientific architecture

- **Type:** framework/concept figure (plans the Method).
- **Should show, left→right / top→down:** China coast → provisional
  bay/region envelope → fixed 10 km analysis cell (EPSG:32651,
  cell_geometry vs bay_clip_geometry) → Observation Event / acquisition
  group (same-datatake multi-tile; contributing-scene QA) →
  modalities (L5/7/8/9 30 m stream; S1 actual-footprint SAR; S2 10 m;
  context layers) → attached label tier (GOLD/SILVER/WEAK/UNLABELED +
  rights), time/phenology, tide/inundation status, provenance record.
- **Must encode:** the 10 km cell is archive/split unit, not a training
  chip; tide modeled vs observed vs proxy separated; UNLABELED ≠
  NEGATIVE; bay envelope PROVISIONAL.
- **Must not encode:** metric numbers or fabricated national maps.
- **Self-sufficiency test:** a reader should reconstruct the
  observation hierarchy without reading Methods prose.
- **Status:** schema specified; rendering NOT authorized yet.

## Fig. 2 — Sensor timeline and dual-resolution streams (1985–2026)

- **Type:** timeline / data-availability schematic.
- **Should show:** L5 (observed 1985–2011 in the three bays), L7
  (1999–2023, SLC status annotated), L8 (2013–), L9 (2022–), S1
  (observed from 2015), S2 (2017–, incl. 2A/2B/2C spacecraft); the
  30 m Landsat-era and 10 m Sentinel-era streams with overlap years,
  and explicit data-gap categories (SENSOR_NOT_OPERATIONAL /
  NO_SCENES_FOUND / NO_QUALITY_SCENES) — gaps are not zero.
- **Status:** schema; numbers from `zhejiang_eo_scene_census_v0`.

## Fig. 3 — Zhejiang three-bay observation-unit design

- **Type:** map schematic (HZB/SMB/YQB) with fixed 10 km grid; insets:
  full cell vs bay-clip geometry; same-datatake multi-tile coverage.
- **Must mark:** envelopes PROVISIONAL; no authoritative shoreline
  implied.
- **Status:** schema; basemap and license to be decided before render.

## Fig. 4 — Pilot-0 baseline / label-arbitration evidence

- **Type:** results figure (candidate: per-model IoU with seed spread +
  SILVER/WEAK Jaccard/arbitration panel; or calibration/patch panel).
- **Constraints:** report means with seed variance; show collapsed
  SegFormer seeds as runs (do not average away); annotate n=7 windows /
  5 components and "no spatial CI; not GOLD".
- **Status:** not selected yet; choose from frozen audit CSVs
  (`pilot0_model_means.csv`, `pilot0_collapse_forensics.csv`).

## Fig. 5 — National scaling design (Issue #14)

- **Type:** architecture/flow schematic ONLY (target-independent
  coastal domain → cells → 2015 SILVER stratification → strata →
  metadata census tiers T0–T3).
- **Hard constraint:** not a national result map; national products do
  not exist. Caption must say design/plan.
- **Status:** schema; blocked pending Issue #14 artifacts.


## Fig. 6 — M2.1b real-pixel integrity evidence

- **Type:** results/mechanism panel (engineering integrity, not
  accuracy).
- **Should show:** (a) schematic of one pilot cell where the nominal
  MGRS frame undercovers but the actual datatake footprint covers fully
  (badge: 5/8 cells, code V0_1_NOMINAL_MGRS_FRAME_UNDERCOVERAGE);
  (b) per-product VALID fractions for the ten S2 products coded
  primary vs EXTRA; (c) S1 VV/VH p01/p50/p99 landed vs independent
  server recompute (deltas $\le$0.116 dB).
- **Must annotate:** 8 cells / 13 products / 121.4 MiB; GOLD = 0;
  no training; single bay, autumn 2022; no national or accuracy claim.
- **Sources:** datasets/manifests/zhejiang_m21b_pilot_v0.json and
  work/m21b/manifests/ZJ_M21B_*.json (frozen).
- **Status:** schema; rendering NOT authorized yet.

## Fig. 7 — 2020 label disagreement vs boundary distance (Issue #18)

- **Type:** results panel (external-map agreement, not accuracy).
- **Should show:** binary disagreement fraction against distance to
  nearest mapped boundary (0--30, 30--60, 60--120, 120--300 m) for
  GEO--CMSA, GEO--CM-SSM and CMSA--CM-SSM on the 30 m native support;
  annotate near/far ratios 7.69, 5.87, 5.90 and the monotone decay.
- **Must annotate:** two documented supports (30 m native grid;
  10 m project lattice); exact fractional cover, no fabricated 5 m
  lattice; GOLD = 0; GEODATA is comparison support, not truth;
  right-inclusive bin edges; seed/support details in
  docs/analysis/2020_LABEL_DISAGREEMENT_AUDIT.md.
- **Must not encode:** accuracy language, per-product ranking, change
  claims, or UNATTRIBUTED region-0 pixels as regional evidence.
- **Candidate ranking (of five analysis figures):** 1 of 5
  (C boundary distance; E coarse-pixel occupancy; D patch size;
  B site panels; A area inventory).
- **Sources:** datasets/manifests/2020_label_scale_audit_v1/table4;
  rendered analysis PNG already exists at
  docs/analysis/figures/figC_boundary_distance.png (analysis
  artifact); in-manuscript final artwork NOT authorized yet.
- **Status:** schema + analysis PNG; manuscript keeps a placeholder.

## Compiled placeholders

`main.tex` renders each figure as a gray placeholder box via
`\figplaceholder{...}` in the section where the figure will live;
replacing a placeholder with artwork requires explicit authorization.
