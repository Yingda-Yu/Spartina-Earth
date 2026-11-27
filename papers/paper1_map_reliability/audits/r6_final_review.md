# R6-09 — Four-Reviewer Final Review (pre-publication)

**Date:** 2026-11-08/09
**Scope:** R6 deliverable set for the EarthArXiv preprint of Spartina Earth
Paper 1. Each reviewer role is assessed strictly against committed evidence
from this round; no claim below rests on unexecuted work.

---

## Reviewer 1 — Remote-sensing scientist (product/agreement science)

**Findings (verified in r6_scientific_integrity.md against committed
artifacts):**
1. All primary national statistics match committed result files:
   IoUs 0.5395 / 0.4444 / 0.3432 with the recorded bootstrap CIs; area span
   519.89–593.71 km² (14.2%); CMSA–GEODATA regional ratio 4.18 [2.74, 7.51].
2. One substantive error was caught and fixed this round: "478 East China
   pixels beyond 50 km" was a Bohai/Yellow value; correct East China count
   is 237 (manuscript corrected).
3. Producer attribution corrected: CMSA is produced by a Capital Normal
   University research team (Crossref-verified affiliations of
   doi:10.1080/01431161.2024.2343136), released via NESDC; the earlier
   "CAS Institute of Coastal Research" claim was contradicted and is now
   removed from §2.1.1, the data inventory, Data Availability, the
   provenance table, and the bib entry.
4. The three South China case windows (Pearl estuary displacement,
   Beibu Gulf GEODATA-only, Leizhou three-way co-location) are documented
   with coordinates and match the committed cluster diagnostics.

**Verdict: PASS.** The paper's central claims are correctly supported and
appropriately hedged (no accuracy claims; explicit shared-domain
assumption).

## Reviewer 2 — Spatial statistician (uncertainty and inference)

1. Spatial block-bootstrap CIs are the committed e5e outputs; the
   reproduction commands are documented in the integrity audit (not re-run
   this round, per the no-new-experiments rule).
2. Regional contrast robustness across five attribution policies
   (ratios 4.06–4.18) is internally consistent with the assignment
   figure regenerated this round: direct 59,440 px, residual 31,201 px of
   90,641 union px (34.4%), overall median 5.5 km, p99 52.48 km — matching
   the committed per-region meta (East China 6.83 km), with the caption now
   explicitly distinguishing overall vs region-specific medians.
3. The densest-window zoom (row 9975, col 12600) is identical to the R4
   window, so the manuscript's figure references remain valid.

**Verdict: PASS.**

## Reviewer 3 — Cartographer (publication-quality figures)

1. **A real defect was found and fixed this round:** the shared
   `add_basemap()` drew Natural Earth geometries in metres against
   kilometre axes, so land fill, coastlines, and province boundaries were
   invisible in every R6 map figure (the earlier QA pass was therefore
   wrong and is superseded — see r6_cartographic_qa.md §0.1). After the
   fix, all four affected figures were regenerated and re-verified by
   pixel counts (land pixels 15.5k → 1.6–1.8M per figure) and visual
   review: cream land vs pale-blue sea, dark coastlines, province lines,
   degree-labelled graticules, scale bars (geodesic-true), north arrows,
   locator insets.
2. A second defect was fixed: suppressed graticule labels previously left
   raw km-number ticks (mixed units) on fig03 panel (a); ticks are now
   cleared when labels are off.
3. All nine manuscript figures use the unified design system;
   product-identity colors (CMSA blue / CM-SSM teal / GEODATA orange) are
   consistent across statistical charts and map overlays; pair-class
   colors in fig03 are explicitly labeled per figure.
4. Basemap licensing: Natural Earth CC0 only; no commercial tiles; no
   sovereignty implications (oceanographic region names).

**Verdict: PASS after fixes.** The correction history is fully documented
rather than hidden, which is the correct integrity behavior.

## Reviewer 4 — Research-integrity reviewer (authorship, claims, licensing)

1. Single-author authorship confirmed (git history co-author check, R6-02);
   no fabricated contributions.
2. Unverified statements were removed or converted to explicit
   placeholders: the fabricated "no external funding" statement was deleted
   (TODO_OWNER comment retained in source); the false "no conflict of
   interest" claim was replaced with an honest Spartina Technology
   affiliation disclosure; the "anonymous reviewers" acknowledgement was
   removed; the AI-use declaration is now an honest assistance statement.
3. Remaining visible `TODO_VERIFY` markers (bib notes, data-inventory and
   license appendix rows) are intentional integrity placeholders per repo
   policy — never fabricated values.
4. Licensing (r6_data_licensing.md): no third-party source bytes are
   redistributed anywhere in the package; the display-derivative tier for
   CMSA/GEODATA and the CM-SSM mirror license conflict remain explicit
   Owner-confirmation blockers, listed in FINAL_CHECKLIST.md.
5. EarthArXiv requirements (r6_eartharxiv_requirements.md) all satisfied by
   the package except owner items (ORCID, license choice, journal line).
6. The submission package carries a coversheet with the required
   non-peer-reviewed statement; visible TODO_OWNER markers there are
   deliberate pre-approval placeholders and are gated by the checklist.

**Verdict: PASS for package assembly; actual submission remains blocked on
the Owner-confirmation items, exactly as designed.**

---

## Consolidated verdict

**READY FOR OWNER APPROVAL — EARTHARXIV PREPRINT**, subject to the
owner-confirmation items recorded in
`submission/eartharxiv/FINAL_CHECKLIST.md` (ORCID, preprint license,
funding/COI/AI-use wording, dataset-license confirmations, legal name,
journal-submission line, and the final explicit authorization to submit).
No critical scientific, statistical, cartographic, or integrity blocker
remains.
