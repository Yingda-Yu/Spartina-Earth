# China external label products — human access actions (v0)

Status: **DESIGNED — NOT EXECUTED**. This document lists the exact manual
steps a human operator must perform to obtain the restricted external
Spartina label products identified in
[CHINA_NATIONAL_ASSET_AUDIT.md](CHINA_NATIONAL_ASSET_AUDIT.md). No
login wall, approval flow or license term has been or will be bypassed
by automation. Credentials must never be entered into scripts or
committed to Git.

Every downloaded archive is treated as **untrusted bytes** until it has
a recorded source passport (provider, portal, DOI, order/approval id,
license, SHA-256, size) under `docs/audit/source_passports/` and a
manifest row under `datasets/manifests/`. Numbers below are quoted from
the audited portal records; anything not observed is marked
`TODO_VERIFY`.

## 0. Consolidated owner-action register (Issue #17 update)

Every blocked label asset the scientific owner (not automation) must act
on. `OWNER_ACTION_REQUIRED` means the asset cannot enter any manifest as
obtained until a human completes the exact action and the source
passport is filled. Portal field values not directly observed are
`TODO_VERIFY`; none are guessed.

| DATASET | WHY_NEEDED | PORTAL | LOGIN_REQUIRED | ORDER_REQUIRED | LICENSE | ESTIMATED_SIZE | EXACT_USER_ACTION | STATUS |
|---|---|---|---|---|---|---|---|---|
| GEODATA 1990 Spartina map (`10.12041/geodata.195159798810196.ver1.db`) | Earliest national reference point; only long-baseline change/recurrence anchor | geodata.cn (Global Change Science Research Data Publishing System); DOI landing page `https://doi.org/10.12041/geodata.195159798810196.ver1.db`; deep link TODO_VERIFY | Yes — personal institutional account | Yes — manual data order (数据订单) with purpose statement and manual approval | RESTRICTED; redistribution `TODO_VERIFY` at order time (2015 product confirmed no-redistribution) | 0.23 MiB per listing (TODO_VERIFY) | Register/login; open DOI; read and screenshot license; submit truthful research/validation purpose; record order id, approver, time, granted license; download approved archive into `work/external/`; SHA-256 + format/CRS passport; never commit bytes | OWNER_ACTION_REQUIRED (BLOCKED_BY_ORDER) |
| GEODATA 2000 Spartina map (`10.12041/geodata.140184217931452.ver1.db`) | Second historical reference point for cross-decade trajectory | same portal; `https://doi.org/10.12041/geodata.140184217931452.ver1.db` | Yes | Yes — data order + approval | RESTRICTED; exact terms TODO_VERIFY | 592 KiB per listing (TODO_VERIFY) | Same as above; record exact projection (listing states Krasovsky/Albers + OBIA) | OWNER_ACTION_REQUIRED (BLOCKED_BY_ORDER) |
| GEODATA 2015 30 m national product (`10.12041/geodata.65372070926827.ver1.db`) | SILVER 2015 stratification already used; must prove local file byte-identity and license | same portal; `https://doi.org/10.12041/geodata.65372070926827.ver1.db` | Yes | Yes — data order + approval | No-redistribution confirmed for this product; exact text snapshot required | Portal value TODO_VERIFY | Order the official archive despite local copy; byte-compare ordered archive vs `old datasets/...2015...tif`; do not treat local copy as licensed until match; record all order metadata | OWNER_ACTION_REQUIRED (local copy: RELATIONSHIP_UNKNOWN until matched) |
| GEODATA 2020 "30 m Spartina" entry (`10.12041/geodata.254533427778392.ver1.db`) | Potential second SILVER national epoch — but title says Spartina, abstract says mangrove | same portal; `https://doi.org/10.12041/geodata.254533427778392.ver1.db` | Yes | Yes, only after content clarification | RESTRICTED; TODO_VERIFY | TODO_VERIFY | Contact the listed data contact in writing first; obtain written confirmation the product is actually Spartina; only then order; keep the reply in the passport | OWNER_ACTION_REQUIRED (EXISTS_WITH_METADATA_CONTRADICTION; hold) |
| CMSA annual Spartina maps 2017–2021 (`10.12199/nesdc.ecodb.mon.2026.013`; mirror CSTR `15732.11.nesdc.ecodb.mon.2026.017` via https://cstr.cn/) | Only multi-year (5-epoch) national series; history stratum flag exists but is empty; recurrence/change evidence | National Ecosystem Science Data Center; DOI landing page; CSTR deep link TODO_VERIFY | Yes — real institutional identity; download needs logged-in purpose statement; short-lived JWT URLs (never share/commit) | Purpose registration (no manual approval observed; TODO_VERIFY) | CC-BY-NC-4.0 as declared; snapshot exact license text at download | 6.1561 GB zip (five per-year products); confirm actual year inventory (listing temporalCoverage text says 2017–2020) | Register; open DOI; accept CC-BY-NC-4.0; submit academic non-commercial validation purpose; browser-download to `work/external/cmsa_2017_2021/`; record holder, purpose, timestamps, JWT issue time, SHA-256, listing, per-year CRS/resolution; no area numbers until manifest audit | OWNER_ACTION_REQUIRED (OPEN_WITH_PURPOSE_REGISTRATION) |
| CM-SSM 2020 (`10.5281/zenodo.16296823`) | SILVER 2020 overlay already integrated (385 cells) | Zenodo (open) | No | No | SOURCE_LICENSE_CONFLICT: Zenodo/DataCite CC-BY-4.0 vs NESDC mirror CC-BY-NC-4.0 — do not assume the permissive term | Already held locally (8 shapefile components, byte-verified) | None for access; owner decision needed only on redistribution/training rights: ask contributor to resolve the license conflict | CLEARED_FOR_ANALYSIS; rights decision OWNER_ACTION_REQUIRED |

No account creation, agreement acceptance, form submission, JWT-URL use,
or re-hosting may be automated (Section 4 below). The GEODATA 2010
product is **not** in this register: no verifiable product was found and
a placeholder must not be invented; re-search is a research task, not an
access action.

## 1. Global Earth Science Data Portal (geodata.cn) — GEODATA products

Provider: National Earth System Science Data Center / Global Change
Science Research Data Publishing System (`geodata.cn`; exact deep-link
pattern to be recorded at order time, `TODO_VERIFY`). DOI links are
stable: prefix every DOI below with `https://doi.org/`.

Common procedure (per product):

1. Open the DOI landing page; read the data-use agreement and license
   (`RESTRICTED` redistribution — the 2015 product is confirmed
   no-redistribution; re-confirm per product).
2. Register / log in to a personal institutional account.
3. Click **data order / 数据订单**, fill the purpose statement
   truthfully (research: Spartina alterniflora long-term remote-sensing
   monitoring; validation/reference use only).
4. Wait for manual approval; record the order id, approver, approval
   time and granted license text into the source passport.
5. Download only the approved archive; do not share the session URL.
6. After download: compute SHA-256, log file count/sizes, fill source
   passport + manifest; never copy bytes into Git (`work/` only).

| Product | DOI (prefix `https://doi.org/`) | Listed size | Current state | Specific action |
|---|---|---|---|---|
| 1990 Spartina map | `10.12041/geodata.195159798810196.ver1.db` | 0.23 MiB listing | BLOCKED_BY_ORDER | order; record archive format + CRS (portal says raster; `TODO_VERIFY`) |
| 2000 Spartina map | `10.12041/geodata.140184217931452.ver1.db` | 592 KiB | BLOCKED_BY_ORDER | order; Krasovsky/Albers CRS + OBIA method stated in listing; record exact projection |
| 2015 30 m national product | `10.12041/geodata.65372070926827.ver1.db` | portal value `TODO_VERIFY` | local copy present, **byte-identity to the ordered archive RELATIONSHIP_UNKNOWN** | order the official archive anyway, then byte-compare with `old datasets/...2015...tif`; do not treat the local copy as licensed until matched |
| 2020 "30 m Spartina" entry | `10.12041/geodata.254533427778392.ver1.db` | `TODO_VERIFY` | EXISTS_WITH_METADATA_CONTRADICTION (Spartina title vs mangrove abstract) | order **only after** asking the data contact to confirm the product is actually Spartina; keep the written reply |

Hard rules for these products:

* Do not use the 1990/2000 products in manuscripts before the order is
  approved and bytes are audited.
* The 2020 GEODATA entry stays `MISSING/contradicted` until the provider
  resolves the title/abstract contradiction.
* Restricted products are validation/reference only; never republish the
  rasters or serve them from SpartinaGuard.

## 2. CMSA annual Spartina maps 2017–2021 (NESDC)

* DOI: `10.12199/nesdc.ecodb.mon.2026.013` →
  `https://doi.org/10.12199/nesdc.ecodb.mon.2026.013`
* Mirror CSTR recorded: `15732.11.nesdc.ecodb.mon.2026.017`
  (resolve via `https://cstr.cn/`; deep link `TODO_VERIFY`).
* Access class: **OPEN_WITH_PURPOSE_REGISTRATION** — browse is open,
  download requires a logged-in purpose statement; links are issued as
  short-lived JWT URLs (do not share or commit them).
* License declared on the NESDC record: **CC-BY-NC-4.0**
  (non-commercial; attribution required; record the exact license text
  snapshot at download time).
* Aggregate archive: **6.1561 GB zip** containing five per-year
  products (2017–2021). Portal metadata defect: temporalCoverage text
  says 2017–2020 while title/description say 2017–2021 — confirm the
  actual year inventory after extraction (`TODO_VERIFY`).

Required human steps:

1. Register an NESDC account with a real institutional identity.
2. Open the DOI page, accept CC-BY-NC-4.0 and submit the purpose
   statement (academic, non-commercial validation).
3. Trigger the JWT download in a browser; save the zip under
   `work/external/cmsa_2017_2021/` (gitignored).
4. Record: account holder, purpose text, approval timestamp, JWT issue
   time, SHA-256, byte size, file listing, per-year CRS/resolution.
5. Do not extract-area or quote per-year numbers until bytes pass the
   manifest audit. The 58,006 ha figure associated with CMSA is a
   single-year (2020) comparator from the CM-SSM paper, not a verified
   per-year series.

## 3. Already-cleared reference product (no action)

* CM-SSM 2020 (`10.5281/zenodo.16296823`): downloaded and
  byte-verified; **SOURCE_LICENSE_CONFLICT** open (Zenodo/DataCite
  CC-BY-4.0 vs NESDC mirror CC-BY-NC-4.0) — analysis/validation only
  until the contributor clarifies; no redistribution decision yet.

## 4. What automation is allowed to do

* Resolve DOIs, read public landing-page metadata, and draft passport
  fields from publicly visible text.
* Verify checksums of archives a human has placed in `work/`.
* It must **not** create accounts, accept agreements, submit purpose
  forms, use exported JWT URLs, or re-host downloaded bytes.
