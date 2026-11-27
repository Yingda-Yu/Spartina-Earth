# R6-07 — Data Licensing / ESG Disclosure Audit (Five Permission Tiers)

**Date:** 2026-11-08
**Sources of record:**
- `DATA_LICENSE.md` (repo root; status key CONFIRMED / KNOWN-POLICY / UNKNOWN)
- `datasets/manifests/china_spartina_label_products_v0.csv` (product registry;
  CMSA rows record `CC_BY_NC_4_0 (declared on NESDC landing page)`; CM-SSM row
  records `SOURCE_LICENSE_CONFLICT`, Zenodo deposit byte-verified)
- `papers/paper1_map_reliability/audits/r4_submission_readiness.md` §S3–S5
- `papers/paper1_map_reliability/audits/r5_submission_declarations.md` §1
- Manuscript Data Availability (`manuscript/main.tex`)

**Tier definitions (per R6 brief):**
1. **Citable** — the product may be cited by DOI/paper in publications.
2. **Analyzable** — the project may compute statistics from an obtained copy
   for scientific purposes.
3. **Displayable-derivative** — derived maps/overlays/statistics made from
   the product may appear in published figures.
4. **Redistributable** — the source bytes may be redistributed by us.
5. **Commercial** — commercial use of the product/derivatives is permitted.

---

## Tier matrix

| Dataset | 1 Citable | 2 Analyzable | 3 Display-derivative | 4 Redistributable | 5 Commercial |
|---|---|---|---|---|---|
| **CMSA 2017–2021** (NESDC release; produced by Capital Normal University team, Li et al. 2024) | YES — DOI 10.12199/nesdc.ecodb.mon.2026.013 + production paper | YES (research use; platform terms + NC) | **PROVISIONAL** — aggregated statistics asserted in manuscript; provider confirmation still TODO (r4 audit S3) | NO | NO (CC BY-NC 4.0 per NESDC landing page) |
| **GEODATA 1990/2000/2015/2020** (IGSNRR / geodata.cn) | YES — DOIs 10.12041/... per layer | YES (research use of ordered copies) | **PROVISIONAL** — CC-BY-NC-ND recorded with unresolved "?" (r4 audit S4); aggregated statistics used; derived mask overlays in figures need provider confirmation if ND is enforced strictly | NO | NO (NC) |
| **CM-SSM 2020** (Zenodo 10.5281/zenodo.16296823, CNU) | YES — Zenodo DOI (byte-verified deposit) | YES | YES under the **Zenodo CC BY 4.0** record; **CONFLICT**: NESDC mirror declares CC BY-NC 4.0 for the same DOI (r4 audit S5) | PROVISIONAL under Zenodo CC BY 4.0 with attribution; blocked while mirror conflict unresolved | CONFLICTED (BY permits, NC forbids) — treat as non-commercial until resolved |
| **Natural Earth 10m** (admin0/admin1/marine) | YES | YES | YES | YES (**CC0 / public domain**, license text archived) | YES |
| **Spartina Earth derived products** (harmonization masks, result CSVs, figures) | YES (our outputs) | YES | YES | **RESTRICTED** — derivatives inherit upstream terms (NC layers ⇒ NC derivatives); code itself Apache-2.0 | NO while NC sources are involved |

## Findings

1. **No source geometry or raster bytes are redistributed in any R6
   deliverable.** The preprint PDF contains only aggregated statistics and
   reduced-resolution derived map images; the submission package contains
   manuscript sources, figures, and CSV result files, never third-party
   source data. This is stated in the manuscript Data Availability and
   repeated in LICENSE_AND_ATTRIBUTION.md.
2. **The display-derivative tier is the legally sensitive one.** For CMSA
   and GEODATA the manuscript asserts publication of aggregated results and
   derived figures, but formal provider confirmation remains an **Owner
   action** (r4 audit S3/S4; both still open). The preprint cannot be
   actually submitted until the Owner either obtains provider confirmation
   or accepts the residual risk explicitly.
3. **CM-SSM mirror conflict** must be resolved or disclosed. Current
   manuscript wording flags the conflict in Data Availability — acceptable
   disclosure; preferred long-term fix is a producer confirmation (Owner
   action, r4 audit S5).
4. **Commercial tier: uniformly NO** for the three Chinese products (NC
   clauses or unresolved terms). Spartina Technology's commercial products
   (SpartinaGuard) must not embed these source datasets or byte-level
   derivatives without separate licensing. This is the ESG-relevant
   disclosure: the open preprint discloses these limits rather than
   overclaiming openness.
5. **CMSA "producer" labels corrected** in R6 (CNU production team; NESDC
   release platform). The r5 audit's "(CAS)" label is historical and
   superseded by the Crossref-verified Capital Normal University
   affiliations; the registry and manuscript are now consistent.

## Owner-confirmation list (feeding FINAL_CHECKLIST.md)

1. CMSA: confirm license (CC BY-NC 4.0 per NESDC landing page) and
   permission to publish derived figures/statistics (r4 S3).
2. GEODATA: confirm CC-BY-NC-ND against the IGSNRR platform record and
   per-layer terms (r4 S4).
3. CM-SSM: resolve the Zenodo CC BY 4.0 vs NESDC mirror CC BY-NC 4.0
   conflict, ideally via producer written confirmation (r4 S5).
4. Spartina Technology formal legal name (used in author affiliation).

**Verdict: nothing in the R6 package redistributes restricted bytes; the
package may be assembled now, but actual submission must wait on Owner
confirmation of items 1–3 (plus ORCID per R6-06).**
