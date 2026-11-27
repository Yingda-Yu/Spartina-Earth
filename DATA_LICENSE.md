# DATA_LICENSE.md

**The Apache-2.0 [`LICENSE`](LICENSE) covers original code in this
repository only. It does not cover datasets, labels, pretrained models, or
third-party products.** Data licenses are confirmed **per asset** and
recorded in that asset's manifest entry (`license`, `permission` fields;
see [`datasets/manifests/schema.json`](datasets/manifests/schema.json)).

## Status key

- **CONFIRMED**: license text and terms located and recorded.
- **KNOWN-POLICY**: the provider's general open-data policy is well
  established, but the exact terms for each accessed version still need to
  be recorded in the asset manifest before redistribution.
- **UNKNOWN**: no reliable terms yet; **do not redistribute or publish
  derived redistributable products** until resolved.

## Data families

| Family | Provider | Intended use | License status | Notes |
|---|---|---|---|---|
| Landsat 5/7/8/9 Collection 2 | USGS | model input / products | KNOWN-POLICY | USGS releases Landsat data as public-domain/open data under its standard Landsat data policy (`https://www.usgs.gov/centers/eros/data-citation`). Record exact scene source and version in manifests; provide standard citation/acknowledgement. `TODO_VERIFY` per released product. |
| Sentinel-1 / Sentinel-2 | European Commission / ESA (Copernicus) | model input / products | KNOWN-POLICY | Copernicus data are generally free and open under the Copernicus regulation/terms; retain Sentinel Data Terms/Copernicus acknowledgement in derived products. `TODO_VERIFY` per released product. |
| HLS | NASA / USGS | optional harmonized input | UNKNOWN (for this project) | Adoption not approved at M0; terms to be reviewed before M1 if used. |
| DEM / tidal / inundation proxies | TBD | context features | UNKNOWN | No specific source selected at M0. |
| Government Spartina mapping products | Chinese government / institutional providers | SILVER labels, comparison | UNKNOWN | Each product's redistribution and publication terms must be checked individually. Do not assume open licensing. |
| Academic Spartina datasets (e.g. 2015 30 m China product transferred into `old datasets/`) | Dataset authors / journal | candidate SILVER labels | UNKNOWN | License, citation requirements, and redistribution rights `TODO_VERIFY` from the dataset's own documentation before any use. |
| Third-party paper data | External authors | comparison / labels | UNKNOWN | Requires contacting authors and recording permission. |
| UAV / field / collaborator data | Collaborators | GOLD labels | UNKNOWN | Governed by separate collaboration agreements; never redistribute without written permission; de-identify institutional details in publications. |
| Model-generated labels (this project) | Spartina Earth | WEAK/SILVER depending on QA | Apache-2.0 for code; data terms inherit upstream inputs | Derived outputs may inherit restrictions from source data. Check composability before release. |

## Rules

1. Never mark Sentinel, Landsat, government, third-party paper, or
   collaborator data as Apache-licensed.
2. Every manifest entry must state license, permission level
   (`internal-only`, `research-only`, `redistributable`, `unknown`), and a
   pointer to the license text or agreement.
3. If permission cannot be established, the asset is `internal-only` and
   is never pushed to Git or publicly redistributed.
4. Data cited in papers must carry a citation and, where required, an
   acknowledgement exactly as specified by the provider.
5. Ethics / IRB / consent statements: never invent. If a venue requires
   specific wording that collaborators have not confirmed, status is
   `NOT READY`.
