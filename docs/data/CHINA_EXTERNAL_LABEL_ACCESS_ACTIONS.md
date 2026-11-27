# China external label products — human access actions (v0)

> **Update 2026-10-06 (M2.4).** The four GEODATA archives and the CMSA
> 2017–2021 archive have been delivered by the owner through the
> legitimate order/purpose channels and are now byte-audited: see
> `datasets/manifests/china_external_label_registry_v1.csv` and
> `docs/audit/CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md`. This v0 document
> is retained as the original action register; per-row STATUS fields
> below now reflect the intake outcome. Remaining owner actions:
> (1) record the four geodata.cn order ids/approver/timestamps and exact
> license snapshots (`TODO_OWNER_RECORD`); (2) record the NESDC purpose
> statement metadata (never the JWT); (3) ask the GEODATA provider to
> correct the **2020 portal abstract** (title/VAT/bytes verified as
> Spartina, abstract is mangrove boilerplate); (4) ask NESDC/producers
> to fix the CMSA stale "2017–2020" time-range text, the "GeoTIFF"
> format error, and to clarify `gridcode=0` semantics. All products
> remain SILVER, `gold_use=FALSE`, reference-only.

Status at authoring: **DESIGNED — NOT EXECUTED**. This document lists the exact manual
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
| GEODATA 1990 Spartina map (`10.12041/geodata.195159798810196.ver1.db`) | Earliest national reference point; only long-baseline change/recurrence anchor | geodata.cn (Global Change Science Research Data Publishing System); DOI landing page `https://doi.org/10.12041/geodata.195159798810196.ver1.db`; deep link TODO_VERIFY | Yes — personal institutional account | Yes — manual data order (数据订单) with purpose statement and manual approval | RESTRICTED; redistribution `TODO_VERIFY` at order time (2015 product confirmed no-redistribution) | 245,971 bytes (240.21 KiB listing; matches delivered RAR) | Register/login; open DOI; read and screenshot license; submit truthful research/validation purpose; record order id, approver, time, granted license; download approved archive into `work/external/`; SHA-256 + format/CRS passport; never commit bytes | **ACQUIRED + AUDITED 2026-10-06** (sha256 8fb616af…; SILVER reference-only); remaining: order metadata TODO_OWNER_RECORD |
| GEODATA 2000 Spartina map (`10.12041/geodata.140184217931452.ver1.db`) | Second historical reference point for cross-decade trajectory | same portal; `https://doi.org/10.12041/geodata.140184217931452.ver1.db` | Yes | Yes — data order + approval | RESTRICTED; exact terms TODO_VERIFY | 606,691 bytes (592.47 KiB listing; matches delivered RAR) | Same as above; record exact projection (listing states Krasovsky/Albers + OBIA) | **ACQUIRED + AUDITED 2026-10-06** (sha256 c55f5a50…; SILVER); minor mangrove-keyword boilerplate noted; order metadata TODO_OWNER_RECORD |
| GEODATA 2015 30 m national product (`10.12041/geodata.65372070926827.ver1.db`) | SILVER 2015 stratification already used; must prove local file byte-identity and license | same portal; `https://doi.org/10.12041/geodata.65372070926827.ver1.db` | Yes | Yes — data order + approval | No-redistribution confirmed for this product; exact text snapshot required | 681,048 bytes delivered RAR | Order the official archive despite local copy; byte-compare ordered archive vs `old datasets/...2015...tif`; do not treat local copy as licensed until match; record all order metadata | **ACQUIRED + AUDITED 2026-10-06** (sha256 470aa027…); extracted TIF BYTE-IDENTICAL to local copy (RELATIONSHIP_UNKNOWN resolved); order metadata TODO_OWNER_RECORD |
| GEODATA 2020 "30 m Spartina" entry (`10.12041/geodata.254533427778392.ver1.db`) | Potential second SILVER national epoch — but title says Spartina, abstract says mangrove | same portal; `https://doi.org/10.12041/geodata.254533427778392.ver1.db` | Yes | Yes, only after content clarification | RESTRICTED; TODO_VERIFY | 695,700 bytes (679.39 KiB listing; matches delivered RAR) | Contact the listed data contact in writing first; obtain written confirmation the product is actually Spartina; only then order; keep the reply in the passport | **ACQUIRED + AUDITED 2026-10-06**: DELIVERED_BYTES_VERIFIED_SPARTINA (sha256 c37bffcd…; VAT 互花米草; positives to 39.35N); PORTAL_ABSTRACT_CONFLICT stays OPEN; owner to request provider correction |
| CMSA annual Spartina maps 2017–2021 (`10.12199/nesdc.ecodb.mon.2026.013`; mirror CSTR `15732.11.nesdc.ecodb.mon.2026.017` via https://cstr.cn/) | Only multi-year (5-epoch) national series; history stratum flag exists but is empty; recurrence/change evidence | National Ecosystem Science Data Center; DOI landing page; CSTR deep link TODO_VERIFY | Yes — real institutional identity; download needs logged-in purpose statement; short-lived JWT URLs (never share/commit) | Purpose registration (no manual approval observed; TODO_VERIFY) | CC-BY-NC-4.0 as declared; snapshot exact license text at download | 6,455,174 bytes (6.1561 **MB**, not GB; prior v0 unit error corrected); all five years 2017–2021 confirmed inside | Register; open DOI; accept CC-BY-NC-4.0; submit academic non-commercial validation purpose; browser-download to `work/external/cmsa_2017_2021/`; record holder, purpose, timestamps, JWT issue time, SHA-256, listing, per-year CRS/resolution; no area numbers until manifest audit | **ACQUIRED + AUDITED 2026-10-06** (sha256 5876d978…; five EPSG:32650 shapefiles; SILVER, CC-BY-NC); remaining: purpose metadata TODO_OWNER_RECORD; gridcode=0 semantics + stale XLS text TODO_VERIFY with NESDC |
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
| 1990 Spartina map | `10.12041/geodata.195159798810196.ver1.db` | 240.21 KiB | ACQUIRED + AUDITED 2026-10-06 (uint8 Krasovsky Albers raster verified; 48,628 positive px) | record order metadata; research-use reference only |
| 2000 Spartina map | `10.12041/geodata.140184217931452.ver1.db` | 592.47 KiB | ACQUIRED + AUDITED 2026-10-06 (284,927 positive px) | record order metadata; research-use reference only |
| 2015 30 m national product | `10.12041/geodata.65372070926827.ver1.db` | 681,048 bytes delivered | ACQUIRED + AUDITED 2026-10-06; local copy BYTE-IDENTICAL to ordered archive (RELATIONSHIP_UNKNOWN resolved; 608,287 positive px) | record order metadata; no redistribution |
| 2020 "30 m Spartina" entry | `10.12041/geodata.254533427778392.ver1.db` | 679.39 KiB | ACQUIRED + AUDITED 2026-10-06: bytes VERIFIED_SPARTINA (577,657 positive px); portal mangrove abstract CONFLICT still open | ask the data contact in writing to correct the portal record; keep the reply |

Hard rules for these products:

* The 1990/2000/2015/2020 archives have been ordered, delivered, hashed
  and audited (`docs/audit/CHINA_EXTERNAL_LABEL_INTAKE_AUDIT_V1.md`);
  use remains restricted to scientific research and validation as
  external references.
* The 2020 GEODATA bytes are admitted as Spartina on byte evidence, but
  the provider's portal abstract conflict stays OPEN until corrected;
  the conflict must be cited alongside any use.
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
* Aggregate archive: **6,455,174 bytes (6.1561 MB; the earlier "GB" was
  a unit error)** containing five per-year products — all years
  **2017, 2018, 2019, 2020, 2021 confirmed present** at intake
  2026-10-06 (EPSG:32650 shapefiles, not GeoTIFF as the XLS states;
  sha256 `5876d978…`). The stale "2017–2020" temporalCoverage text and
  the GeoTIFF/38 MB format field are confirmed metadata defects; owner
  to report them to NESDC. `gridcode=0` semantics remain
  `TODO_VERIFY` with the producers.

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

**Outcome 2026-10-06:** archive delivered, byte-audited and registered
(`NESDC-CMSA-2017…2021` in registry v1); measured positive (gridcode 2)
areas 494.69/504.31/532.99/571.35/586.51 km²; SILVER, CC-BY-NC,
reference-only; `gridcode=0` features excluded as UNKNOWN.

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
