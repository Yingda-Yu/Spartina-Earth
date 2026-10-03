# CLAIM → CITATION → SUPPORT audit — Spartina Earth v0

Phase 3 (Issue #15), 2026-10-03. Protocol: DOI/resolver existence was
already verified for all 38 references (see `literature_matrix.md`);
existence is **not** treated as support. For the highest-impact external
claims below, the cited source's title/abstract/full text (where open)
was checked against the exact manuscript sentence. Verdicts:
SUPPORTED = the source states the claim; PARTIAL = the source supports
part of the sentence (claim narrowed below); UNSUPPORTED = replaced or
removed. This audit covers 18 claims across the required themes.

| # | Theme | Manuscript claim (location) | Cited source(s) checked | Verdict | Action taken |
|---|---|---|---|---|---|
| 1 | Invasion history | "Deliberately introduced to China in 1979" (§1) | wang2010benthic, zheng2018productivity | PARTIAL | Both papers are thematically about impacts/productivity; the 1979 date was not verified in their abstracts. Added CrossRef-verified primary-support citation wang2018soilcarbon (Sci. Rep. 8:628, 2018, 10.1038/s41598-017-19111-1), which states the 1979 introduction in its open-access text. |
| 2 | Ecological effects | "Altering sediment dynamics, benthic habitat, and hydrology" (§1) | zheng2018productivity (productivity meta-analysis), wang2010benthic (benthic communities only) | PARTIAL | Refs support benthic-community effects and marsh productivity, not sediment/hydrology directly. Narrowed sentence to benthic habitat, productivity, and soil/ecosystem consequences with the verified source. |
| 3 | National historical mapping | "Rapid, spatially heterogeneous invasion at national scale from Landsat time series" (§1) | liu2018rapid (Landsat OLI 2014–2016, OBIA+SVM), mao2019rapid (Landsat 1990–2015 multi-temporal) | SUPPORTED | mao2019 is the true time-series source; liu2018 is multi-year national mapping. Bundle retained; sentence already says "time series" and is carried by mao2019. |
| 4 | Human prevention | "National analyses linking patterns to coastal engineering and prevention effort" (§2) | mao2019rapid | SUPPORTED | Title/abstract explicitly cover "Spatiotemporal Patterns and Human Prevention"; reported +50,204 ha over 25 years. |
| 5 | Phenology | "Phenology-driven mappability varies with latitude; seasonal window shifts with latitude" (§1, §2) | zhang2022latitudinal | SUPPORTED | Paper quantifies latitudinal LSP variation of S. alterniflora via Landsat 7/8 + Sentinel-2; directly supports the window-shift claim. |
| 6 | Eradication/recurrence | "Expansion modes that include dieback and post-treatment regrowth" (§1) | yan2023monitoring | PARTIAL | Abstract supports expansion modes and dieback drivers in Yancheng; it does not establish post-treatment regrowth. Narrowed to "expansion modes and documented dieback"; the management/regrowth clause is carried only by yuan2011cutting. |
| 7 | Management efficacy | "Cutting combined with waterlogging demonstrably alters regrowth" (§1) | yuan2011cutting | SUPPORTED | The study is a field control experiment of cutting + waterlogging on S. alterniflora in the Yangtze estuary; claim matches its purpose and findings. |
| 8 | Estuary high-resolution mapping | "High-resolution time series mapped the species through phenology in the Yangtze estuary" (§2) | ai2017phenology | SUPPORTED | GF-1 WFV time-series, phenology-based mapping, Yangtze estuary — direct. |
| 9 | Estuary multi-source mapping | "Multi-source optical imagery supported mapping in the Zhangjiang estuary" (§2) | liu2017monitoring | SUPPORTED | Title matches exactly. |
| 10 | Tide effects | "Inundation changes the apparent surface between acquisitions" (§1, §2) | oconnell2017tmii | SUPPORTED | TMII is an inundation filter to flag flooded pixels and improve tidal-marsh time-series analysis; the claim is the mechanism that paper operationalizes. |
| 11 | Intertidal change | "Global tidal-flat inventories show intertidal extent changes with acquisition conditions and over decades" (§2) | murray2019tidalflats | SUPPORTED | Nature 2019 global trajectory 1984–2016 (>30 years, satellite epoch quantiles) — direct. |
| 12 | SAR usefulness | "Joint S1/S2 classification of complex coastal wetlands confirms combining optical and radar is valuable" (§2) | jamali2022swin | SUPPORTED (wording softened) | Abstract is a Swin/CNN comparison using integrated S1+S2 for complex coastal wetlands. One study "illustrates" rather than "confirms"; softened. |
| 13 | Sensor-era facts | "L5/7/8/9 supply 30 m record from the 1980s; S1 C-band and S2 10–20 m from mid-2010s" (§1) | wulder2012archive, torres2012s1, drusch2012s2, masek2020l9 | SUPPORTED | Mission/archive papers and the L9 continuity paper state these dates and specifications. |
| 14 | Product dB fact | "S1_GRD products are already calibrated to decibels; a second 10log10 is forbidden" (§4) | none (platform product documentation) | PARTIAL | True for the GEE collection's backscatter bands per GEE product docs, but no peer-reviewed citation is attached. Kept, with an explicit "GEE product documentation; technical reference TODO_CITATION" marker (matches literature_matrix known-gap list). |
| 15 | Cross-sensor/cross-region generalization | "Cross-region, cross-date and cross-sensor shifts degrade classification and require explicit treatment" (§1, §2) | tuia2016da (DA survey), luo2022crossspatiotemporal | SUPPORTED | Survey + specific cross-spatiotemporal DA study; claim is deliberately general. |
| 16 | Spatial leakage | "Random-pattern validation with spatial autocorrelation produces optimistic accuracy" (§1, §2) | roberts2017cv, ploton2020spatial | SUPPORTED | Both are the canonical structured-CV / spatial-validation references; direct. |
| 17 | Foundation-model literature | SatMAE, CROMA, Prithvi, DOFA characterized as temporal/multimodal pre-training (§2) | cong2022satmae, fuller2023croma, jakubik2024prithvi, xiong2024dofa | SUPPORTED | Titles/venues match each characterization; sentence explicitly says they motivate a future goal, not that they are used. |
| 18 | Long-term archive premise | "Opening of the Landsat archive created the evidentiary basis for multi-decadal monitoring" (§2) | wulder2012archive | SUPPORTED | Wulder et al. 2012 RSE, the standard free-and-open Landsat archive reference. |

## Residual open items (do not silently close)

- FES2022b peer-reviewed reference still absent; FES2014 lineage cited
  with deployment status unchanged.
- ALOS/PALSAR L-band product paper pending registry decision.
- Eradication/recurrence quantitative literature beyond yuan2011/
  yan2023 to be added only when a specific recurrence claim is made.
- All national CMSA per-year accuracy figures remain TODO_VERIFY.
