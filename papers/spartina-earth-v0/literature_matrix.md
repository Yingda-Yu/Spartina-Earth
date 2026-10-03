# Literature Matrix — Spartina Earth v0

Verification protocol (executed 2026-10-03):

1. Each entry was fetched from the CrossRef metadata API by DOI
   (`https://api.crossref.org/works/<DOI>`); title, author list, year,
   venue and DOI were cross-checked against the returned record.
2. The one arXiv-only entry (DOFA) was verified against the arXiv API.
3. No entry is included from model memory; unverified candidates were
   discarded. Records to add later must follow the same protocol and be
   added to `references.bib` only after verification.

Coverage follows Issue #15: invasion/eradication/recurrence; China
coastal mapping; long-term optical monitoring; S1/S2 wetland mapping;
SAR–optical fusion; phenology/tide; cross-sensor/domain generalization;
EO foundation/temporal representation models; validation leakage; data
provenance; platforms and auxiliary datasets.

## A. Spartina ecology, invasion, management and remote sensing

| Bib key | Year | Venue | Role in paper | Verified |
|---|---|---|---|---|
| liu2018rapid | 2018 | Remote Sensing | Landsat observations of rapid S. alterniflora invasion in mainland China | DOI CrossRef |
| mao2019rapid | 2019 | Sensors | National spatiotemporal invasion patterns and human prevention | DOI CrossRef |
| ai2017phenology | 2017 | J. Applied Remote Sensing | Phenology-based mapping with high-resolution time series, Yangtze estuary | DOI CrossRef |
| liu2017monitoring | 2017 | Remote Sensing | Multi-source high-resolution mapping, Zhangjiang estuary | DOI CrossRef |
| zhang2022latitudinal | 2022 | RSE | Latitudinal variation in S. alterniflora land-surface phenology across China — season-window justification | DOI CrossRef |
| yan2023monitoring | 2023 | Remote Sensing | Expansion mode and dieback monitoring, Yancheng — recurrence/dieback precedent | DOI CrossRef |
| yuan2011cutting | 2011 | Estuar. Coast. Shelf Sci. | Cutting + waterlogging control efficacy — management intervention precedent | DOI CrossRef |
| zheng2018productivity | 2018 | Ecological Engineering | Meta-analysis of invasive saltmarsh productivity along China's coast | DOI CrossRef |

## B. Platforms, sensors, analysis-ready data and QA

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| gorelick2017gee | 2017 | RSE | Google Earth Engine planetary-scale platform | DOI CrossRef |
| wulder2012archive | 2012 | RSE | Opening of the Landsat archive — long-term monitoring premise | DOI CrossRef |
| masek2020l9 | 2020 | RSE | Landsat 9 continuity | DOI CrossRef |
| torres2012s1 | 2012 | RSE | Sentinel-1 mission (C-band SAR, GRD) | DOI CrossRef |
| drusch2012s2 | 2012 | RSE | Sentinel-2 mission | DOI CrossRef |
| gascon2017s2 | 2017 | Remote Sensing | Sentinel-2A calibration and product validation | DOI CrossRef |
| esa2022s2l2a | 2022 | ESA dataset DOI | Sentinel-2 MSI L2A BOA reflectance (SCL scene classification source) | DataCite DOI |
| zhu2015fmask | 2015 | RSE | Fmask4 cloud/shadow/snow detection, Landsat + Sentinel-2 | DOI CrossRef |
| claverie2018hls | 2018 | RSE | Harmonized Landsat–Sentinel-2 (context for dual-stream policy; HLS not adopted) | DOI CrossRef |

## C. Environmental context layers (national registry)

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| pekel2016gsw | 2016 | Nature | JRC Global Surface Water, water context | DOI CrossRef |
| murray2019tidalflats | 2019 | Nature | Global distribution/trajectory of tidal flats (online 2018) | DOI CrossRef |
| lyard2021fes | 2021 | Ocean Science | FES2014 tide atlas (predecessor line to FES2022b selected-not-deployed) | DOI CrossRef |
| oconnell2017tmii | 2017 | RSE | Tidal Marsh Inundation Index — inundation filtering, tide confound | DOI CrossRef |
| munoz2021era5land | 2021 | ESSD | ERA5-Land reanalysis for climate context | DOI CrossRef |
| esa2022copdem | 2022 | ESA dataset DOI | Copernicus DEM GLO-30 elevation context | DataCite DOI |

## D. Multimodal wetland mapping

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| jamali2022swin | 2022 | Water | Joint Sentinel-1/Sentinel-2 deep coastal wetland classification (SAR–optical fusion precedent) | DOI CrossRef |

## E. Temporal and multimodal EO representation (related work; not claimed as used)

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| russwurm2020selfattn | 2020 | ISPRS J. | Self-attention for raw optical satellite time series | DOI CrossRef |
| garnot2020pixelset | 2020 | CVPR | Pixel-set encoders with temporal self-attention for SITS | DOI CrossRef |
| yuan2022sitsformer | 2022 | IJAEOG | SITS-Former pretrained spatio-spectral-temporal model | DOI CrossRef |
| cong2022satmae | 2022 | NeurIPS | SatMAE pre-training for temporal/multi-spectral imagery | DOI CrossRef |
| fuller2023croma | 2023 | NeurIPS | CROMA contrastive radar–optical masked autoencoders | DOI CrossRef |
| jakubik2024prithvi | 2024 | preprint (SSRN) | Prithvi generalist geospatial foundation model | CrossRef/SSRN DOI |
| xiong2024dofa | 2024 | arXiv | DOFA neural-plasticity multimodal EO foundation model | arXiv API |

## F. Cross-sensor / cross-region generalization

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| tuia2016da | 2016 | IEEE GRSM | Domain adaptation for RS classification — survey framing | DOI CrossRef |
| luo2022crossspatiotemporal | 2022 | ISPRS J. | Cross-spatiotemporal land-cover classification with deep DA | DOI CrossRef |

## G. Validation, leakage and data provenance

| Bib key | Year | Venue | Role | Verified |
|---|---|---|---|---|
| roberts2017cv | 2017 | Ecography | CV strategies for spatial/temporal structured data | DOI CrossRef |
| ploton2020spatial | 2020 | Nat. Commun. | Spatial validation reveals optimistic large-scale ecological mapping | DOI CrossRef |
| gebru2021datasheets | 2021 | CACM | Datasheets for datasets | DOI CrossRef |
| mitchell2019modelcards | 2019 | FAT* | Model cards for model reporting | DOI CrossRef |

## Known gaps to fill in later rounds (do not cite until verified)

- A dedicated Sentinel-1 GRD dB/scaling product reference beyond the
  mission paper and ESA user guide (the COPERNICUS/S1_GRD dB fact is
  documented from product documentation, to be cited as a technical
  reference in the M2.1b byte-validation report).
- Peer-reviewed FES2022 / FES2022b reference (currently cite FES2014
  lineage + official model documentation; deployment status unchanged).
- ALOS/PALSAR L-band product paper — pending Issue #14 registry decision
  on accessibility/licensing.
- Eradication/recurrence quantitative studies beyond
  yuan2011cutting/yan2023monitoring — add when a specific recurrence
  claim requires them.
