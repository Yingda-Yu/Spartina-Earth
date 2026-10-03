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
