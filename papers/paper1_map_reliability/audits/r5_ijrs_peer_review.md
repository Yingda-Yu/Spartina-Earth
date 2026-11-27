# R5-10 — Independent Five-Perspective Peer Review (IJRS-targeted)

**Manuscript:** Spatial Agreement and Regional Uncertainty in Multi-Source
Maps of *Spartina alterniflora* along the Chinese Coast
**Review basis:** compiled 31 pp manuscript (2026-11-08 build), R4/R5 audit
trail, results files, submission package
**Stance:** critical, evidence-based; no automatic acceptance. Each reviewer
gives specific major/minor concerns and a recommendation.

---

## Reviewer 1 — Remote sensing products reviewer

**Major concerns.**
1. *Representation confounded with detection.* Comparing a sub-meter clump
   vector product against 10 m and 30 m raster products at a 100 m harmonized
   grid partially conflates thematic disagreement with representation
   differences. The rasterization-rule sensitivity (up to 29 % IoU shift) and
   the 30 m multi-resolution check (≤0.4 % shifts) mitigate this, but the
   manuscript should state more explicitly that the measured agreement is
   agreement *after harmonization*, i.e., an operational comparability
   envelope, not a pure detection-level agreement.
2. *GEODATA presence-only semantics.* Value 255 is a uniform fill, not a
   valid-observed-absence class. The manuscript handles this honestly
   (explicit "not mapped as presence == absence" assumption, coverage
   audit), but the South China GEODATA-larger-extent finding should be
   caveated against the possibility of over-mapping presence in the GEODATA
   lineage at 30 m with mixed pixels.
3. *Within-year phenology windows.* The 2020 "common year" does not
   guarantee common acquisition windows; *S. alterniflora* phenology differs
   strongly between the Bohai and South China coasts, and each product's
   within-year image composition is undocumented in the compared metadata.
   A short discussion addition is warranted.

**Minor.** (i) Sentinel-2 vs Landsat-class spectral resolution difference
should be listed among disagreement sources explicitly; (ii) fig03 "neither"
class swatch contrast is low.

**Recommendation.** Minor revision. The agreement-not-accuracy framing is
correct and consistently maintained; the three concerns above are
addressable with text changes and do not require new experiments.

## Reviewer 2 — Geospatial statistics reviewer

**Major concerns.**
1. *Block bootstrap adequacy.* IoU is a ratio over the whole domain; 2 km
   blocks may be smaller than the autocorrelation range of large clumps
   (largest CM-SSM patch 746 ha ≈ 2.7 km across; assignment p99 distance
   50.4 km). If block-size sensitivity (3–10 km) was run, the manuscript
   must report those results in the main text or SI; if CI widths change
   materially with block size, the 2 km CIs are anti-conservative and the
   widest-block intervals should be quoted.
2. *Ratio inference in a small region.* The Bohai/South-China ratio for
   CMSA–GEODATA has a small-denominator region (South China IoU ≈ 0.13).
   The reported lower bounds (2.58–2.78 across policies) are comfortably
   above 1, so the qualitative conclusion survives, but the paper should
   note the skew of ratio distributions with small denominators.
3. *Multiple comparisons.* Three pairs × three regions × five policies are
   contrasted without adjustment; conclusions rest on consistent direction
   rather than any single test, which is fine, but a one-sentence
   acknowledgment is needed.

**Minor.** (i) The "effective sample size ≈ 2,000 blocks" paragraph is good
practice and should stay; (ii) report the bootstrap seed (202601 — already
stated) with each CI table.

**Recommendation.** Minor revision. The inference machinery is sound and the
regional conclusion is robust; report block-size sensitivity numbers and add
the two acknowledgments.

## Reviewer 3 — Coastal ecology reviewer

**Major concerns.**
1. *Phenological asymmetry as a candidate driver.* The regional IoU
   heterogeneity is described but under-interpreted: southern populations
   are quasi-evergreen while northern populations senesce, so products built
   from different seasonal composites (Sentinel-2 annual mosaics vs Landsat
   growing-season vs VHR single scenes) face systematically different
   separability along the coast. This is a plausible, citable mechanism
   candidate that the discussion mentions only in passing via "thematic
   encoding".
2. *Management consequence asymmetry.* Low agreement in the South China Sea
   — where eradication is active under the 2022–2025 action plan — has
   larger operational cost per unit area than in the Bohai, because
   management units there are smaller and more fragmented. The
   recommendations section could rank the practical guidance by region.

**Minor.** (i) The 1979 introduction citation chain (Li 2009; Zhang 2023) is
appropriate; (ii) the Zhejiang/Fujian hotspot discussion is well grounded in
the actual cluster analysis.

**Recommendation.** Minor revision. No new analyses required; the paper
correctly refuses to adjudicate which product is "right" and the ecological
framing is defensible.

## Reviewer 4 — Reproducibility reviewer

**Major concerns.**
1. *Source-data availability.* CMSA and GEODATA are institutional releases
   with unverified licenses and no public formal citations; CM-SSM is on
   Zenodo (DOI recorded, mirror-side license conflict flagged). A reader
   cannot independently re-run the pipeline without obtaining CMSA/GEODATA
   through the providers. The manuscript says this, but the checklist items
   must be closed before publication for the reproducibility claim to hold.
2. *Placeholder metadata.* `TODO_VERIFY` marks remain in two bib notes, the
   appendix license table, and the AI-use declaration; all are visible in
   the compiled PDF. These must be resolved or they will embarrass the
   authors in review.

**Positives.** Harmonization scripts, bootstrap code, per-experiment seeds,
configuration, result CSVs, and the full audit trail (R1–R5) are committed;
the superseded meridian-band analysis is disclosed in SI rather than hidden;
numerical claims trace to result files (re-checked in R4-08 and R5-06).

**Recommendation.** Major revision *administratively* (resolve placeholders
and licensing), minor scientifically. Reproducibility infrastructure is above
the standard for the field.

## Reviewer 5 — Handling editor (IJRS)

**Journal fit.** Strong. The journal published the CMSA production paper
(Li et al. 2024, IJRS 45(9)) and recent product-assessment and coastal
wetland studies; a national multi-product reliability analysis with
uncertainty quantification is squarely in scope. Length (~31 pp, ~10,200
words, 8 figures, 12 tables) is acceptable for a data-rich methodological
study. Abstract (281 words) and structure comply with the Instructions for
Authors.

**Major concerns.**
1. The manuscript cannot be submitted in its current state: author block
   anonymized with TODOs, generative-AI declaration unresolved, funding
   and competing-interest statements unconfirmed, and two dataset licenses
   unverified. These are desk-reject or integrity risks.
2. The removed-fabricated-references episode (12 unverifiable entries in
   earlier drafts, documented in the related-work matrix) is now resolved,
   but the owner should be aware that the final bibliography rests on 17
   verified/placeholder-marked entries and two placeholders still need
   provider citations.

**Assessment.** Scientifically: the paper asks a modest, answerable question
and answers it with appropriate statistical care and unusually honest
limitations. The 4.06–4.18× regional contrast, its robustness across
attribution policies, and the agreement-not-accuracy framing are the
strongest elements. The claim structure avoids overreach (spatial
displacement is presented as consistent-with, not conclusive).

**Recommendation.** Ready for owner completion of the administrative
checklist, then submit. Expected outcome at IJRS: minor-to-moderate revision
from technical reviewers; the main revision risks are the block-bootstrap
justification (Reviewer 2 concern 1) and the phenology-window discussion
(Reviewer 1 concern 3 / Reviewer 3 concern 1), both addressable in text.

---

## Consolidated verdict

**Not automatically acceptable — conditional on:**
- (editorial) closure of all owner-dependent items in
  `submission/ijrs/author_funding_coi_checklist.md`;
- (integrity) resolution of the two dataset placeholder citations.

**Technical items closed in-text during the same R5 pass (2026-11-08):**
- Reviewer 2 concern 1 → the Block-size sensitivity paragraph now also
  reports the regional result: CMSA–GEODATA Bohai/Yellow and South China
  point estimates move only 0.5599→0.5557 and 0.1341→0.1323 between 1 and
  10 km blocks, and even at 10 km the regional intervals do not overlap
  ([0.471, 0.633] vs [0.056, 0.223]).
- Reviewer 1 concern 1 / Reviewer 3 concern 1 → the Methods now state that
  reported agreement is an operational comparability envelope
  (agreement after harmonization), and the Discussion adds the
  phenological-window-mismatch hypothesis with an explicit statement that it
  cannot be tested from the compared metadata.
- Reviewer 2 concerns 2–3 (ratio skew with small denominators; multiple
  comparisons) are partially covered by the existing text (wide CIs quoted,
  conclusions resting on direction-consistent results); if the journal
  reviewers press, they are one-sentence additions.

**Genuine readiness for IJRS submission: YES, after the owner completes the
administrative gates above. No scientific redesign is required.**
