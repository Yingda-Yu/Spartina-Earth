# License and Attribution Statement

**Preprint:** Spatial Agreement and Regional Uncertainty in Multi-Source
Maps of *Spartina alterniflora* along the Chinese Coast (Spartina Earth
Paper 1)
**Author:** Yingda Yu (Wenzhou-Kean University; Spartina Technology)

## Manuscript and code

- Manuscript text, figures, and tables: © 2026 Yingda Yu. The distribution
  license for the preprint (e.g. CC BY 4.0) is selected in the EarthArXiv
  submission form — **TODO_OWNER**.
- Analysis and figure code in the Spartina Earth repository: Apache-2.0.
- Full provenance chain (source → preprocessing → result) is recorded in
  the repository's audits and manifests.

## Third-party datasets used (never redistributed in this submission)

No third-party source geometry or raster bytes are included in the
submission PDF, the source zip, or this package. Only aggregated statistics
and derived map images derived from the following products appear:

1. **CMSA 2017–2021** (10 m, China Coastal Saltmarsh Atlas). Production
   study: Li et al. (2024), Int. J. Remote Sens.
   (doi:10.1080/01431161.2024.2343136). Released via the National Earth
   System Science Data Center (doi:10.12199/nesdc.ecodb.mon.2026.013);
   CC BY-NC 4.0 declared on the NESDC landing page (record in
   `datasets/manifests/china_spartina_label_products_v0.csv`). Used under
   research-only terms; formal provider confirmation of publication of
   derived statistics/figures: **TODO_OWNER** (r4 audit S3).
2. **GEODATA 1990/2000/2015/2020** (30 m, IGSNRR / geodata.cn, DOIs
   10.12041/... per layer). Platform terms recorded as CC BY-NC-ND with
   an unresolved verification flag — **TODO_OWNER** (r4 audit S4). Ordered
   copies used read-only for analysis.
3. **CM-SSM 2020** (sub-meter, Capital Normal University). Zenodo deposit
   doi:10.5281/zenodo.16296823 declares CC BY 4.0 (byte-verified local
   copy); the NESDC mirror of the same DOI declares CC BY-NC 4.0 — mirror
   conflict flagged in the manuscript Data Availability and pending
   producer confirmation (**TODO_OWNER**, r4 audit S5).

Because two of the three products carry non-commercial (NC) terms (and the
third is conflicted), **all derived map images and statistics in this
preprint that incorporate those products inherit non-commercial
conditions**. Commercial reuse requires separate licensing from the data
producers.

## Basemap data

- **Natural Earth 1:10m** (admin-0 countries, admin-1 provinces, marine
  polygons): public domain (CC0). No attribution required; credited in
  figure captions as good practice. License text archived at
  `docs/audit/source_passports/2016/naturalearth/*/license.txt` and
  source passports under `work/external/`.
- **IHO-derived sea-region groupings** (Bohai/Yellow, East China, South
  China): compiled from Natural Earth marine polygons for regional
  stratification; public-domain basis, no sovereignty statement implied.
  Region names are oceanographic, not political.

## Attribution requirements when reusing this preprint's results

- Cite the preprint DOI (assigned by EarthArXiv).
- When reusing numbers derived from CMSA/GEODATA/CM-SSM, additionally cite
  the respective source products and their production papers as listed in
  the manuscript references.
- The repository's result CSVs and harmonization masks are derived from
  restricted-licence products and are shared for verification and research
  use, not for unrestricted redistribution.
