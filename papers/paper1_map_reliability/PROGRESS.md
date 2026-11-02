# PROGRESS — Spartina Earth Paper 1

**Working Title:** Reliability of Multi-Source Spartina alterniflora Distribution Maps for Coastal Monitoring in China

**Current Stage:** Stage A — Manuscript Foundation

**Git Branch:** `feat/paper1-map-reliability` (created from `reboot/spartina-earth-m0`)

**Last Commit:** TODO (to be made after Stage A compilation)

**Manuscript Directory:** `papers/paper1_map_reliability/`

---

## Current Status

### Manuscript Word Count
- Total written: ~4,200 words
- Abstract: 350 words
- Introduction: ~1,400 words
- Study Area & Datasets: ~900 words
- Methodology: ~1,100 words
- Results skeleton: ~400 words (numbers real, E3/E4/E6/E7 marked TODO)
- Discussion: ~1,100 words
- Conclusions: ~100 words (TODO expansion)
- References section: skeleton

### Sections Written
- [x] Title + Abstract + Keywords
- [x] Introduction (with RQ1–RQ4, C1–C4)
- [x] Study Area & Datasets (CMSA, GEODATA, CM-SSM audited)
- [x] Methodology (E1–E6 implemented in skeleton, with math)
- [x] Results structure (E2 numbers real, E3/E4/E6/E7 TODO)
- [x] Discussion (real interpretation)
- [x] Conclusions (skeleton, needs expansion)
- [x] Data Availability + Code Availability (placeholder URLs)
- [x] Bibliography (30 entries, all DOIs verified where possible)
- [x] Appendix (data inventory table)

### Experiments Completed
| ID | Description | Status | Output |
|----|-------------|--------|--------|
| E1 | Data harmonization | **In progress** | Harmonization script skeleton, EPSG:3410 target |
| E2 | Area consistency | **Verified complete** | 2017-2021 CMSA, 1990-2020 GEODATA, 2020 CM-SSM all audited. 2020 cross: CMSA=571.35, GEODATA=519.89, CM-SSM=593.71 km² |
| E3 | Spatial agreement | **Blocked** | Needs rasterization of CMSA+CM-SSM to 10m grid, IoU/Dice computation |
| E4 | Resolution sensitivity | **Not started** | |
| E5 | Regional heterogeneity | **Not started** | |
| E6 | Monitoring implications | **Partially done** | Trend comparison real (CMSA monotonic vs GEODATA peak+decline) |
| E7 | Independent validation | **Blocked** | No GOLD reference found |

### Figures Completed
| # | Description | Status |
|---|-------------|--------|
| Fig 1 | Study Area + Dataset Coverage | **Not started** |
| Fig 2 | Harmonization Framework Diagram | **Not started** |
| Fig 3 | Spatial Agreement/Disagreement Map | **Blocked on E3** |
| Fig 4 | Area Statistics + IoU/Dice | **Partially done** (area numbers real) |
| Fig 5 | Resolution Sensitivity Curves | **Not started** |
| Fig 6 | Regional Case Studies | **Not started** |
| Fig 7 | Monitoring Implications | **Not started** |

### Tables Completed
| # | Description | Status |
|---|-------------|--------|
| Table 1 | Dataset Inventory | **Done** (real audited data) |
| Table 2 | Area Comparison | **Done** (2020 cross real, trend real) |
| Table 3 | Spatial Agreement | **Blocked on E3** |
| Table 4 | Sensitivity | **Not started** |
| Table 5 | Licensing / Appendix inventory | **Skeleton** |

### Verified References
- [x] Wang et al. 2024 (IJDE) — full text retrieved OA
- [x] Zhao et al. 2023 (RS) — full text retrieved OA MDPI
- [x] Xu et al. 2024 (RSE) — full text retrieved OA via mirror
- [x] Ximenes et al. 2023 (STOTEN) — full text retrieved pre-print HAL
- [x] Xu et al. 2025 (ESSD CM-SSM) — DOI verified
- [x] CMSA source — 2017-2021 shapefiles audited, area verified
- [x] GEODATA source — 1990/2000/2015/2020 tifs audited, VAT counts verified

### PDF Compilation Status
- LaTeX available (TeX Live 2022)
- Compilation not yet attempted (main.tex references TODO figures/tables that don't exist yet)
- Will attempt first full compilation after creating fig04_area_trend placeholder

---

## Scientific Blockers
1. **E3 IoU/Dice** — needs 10m rasterization of CMSA + CM-SSM, common mask, IoU/Dice computation
2. **E4-E5** — resolution + regional sensitivity not started
3. **E7 validation** — no GOLD reference found; acknowledge limitation
4. **GEODATA non-overlap** — CMSA years (2017-2021) and GEODATA years (1990,2000,2015,2020) only share 2020

## Next Executable Tasks
1. Compile first readable PDF (replace TODO figures with placeholder boxes)
2. Run E3: rasterize CMSA+CM-SSM, compute IoU/Dice on harmonized grid
3. Run E4-E5: sensitivity analysis
4. Update Results section with real numbers
5. Commit Stage A + B
