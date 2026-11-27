# V022_IMPACT_ANALYSIS — protocol options A/B/C

Analyzes the three protocol options against: the 35 repair products, the
original 53-cell panel, the 24-cell sealed reserve, and the future
benchmark. No option was executed; this is a decision document.

## Option A — keep current v0.2 contract, remain NOT_READY

- **35 repair products**: unchanged; `V021_R00372-C00139_L8_2015_E`
  stays a hard error; accepted denominator 34; the cell keeps both-year
  support via other slots.
- **53-cell panel**: unchanged; its `QA_PASS_WITH_HONEST_SOURCE_REJECTIONS`
  verdict stands (all its classifications remain valid under the frozen
  contract).
- **Reserve**: unchanged (24 cells untouched by any QA event).
- **Benchmark**: stays blocked. GEODATA gate thresholds are met on the
  QA-clean denominator (15/12/5) but the frozen readiness semantics
  require a QA batch verdict in {QA_PASS, QA_PASS_WITH_HONEST...} →
  NOT_READY persists.
- **Cost of A**: the program remains closed by an artifact of an
  untested precondition (146+22 historical partial-finite acceptances
  prove partial gaps were never themselves disqualifying), and the same
  phenomenon would re-occur in any future export (expected rate: 1
  zero-valid per ~350 optical products so far: 2 in 478).

## Option B — formal v0.2.2 honest-source-rejection classification

Change: replace the all-finite precondition with the five-condition test
in `V022_QA_PROTOCOL_PROPOSAL.md` §3 (byte-faithful + grid + physical
audit + mask gate + non-finite pixels confined to non-clear classes).

- **35 repair products**: the single failure reclassifies to
  `ZERO_QA_VALID_SURFACE_PIXELS`; batch becomes
  `QA_PASS_WITH_HONEST_SOURCE_REJECTIONS`; accepted denominator stays 34
  products / 12 cells (the failed product remains **counted out** of
  support — identical counts either way).
- **53-cell panel — retroactivity check**: exactly **0** changes. Its
  single zero-valid case already satisfied the stricter precondition
  (100 % finite), and its 146 partial-finite products have VALID > 0, so
  they are untouched by any precondition change. No past verdict moves.
- **Reserve**: unchanged; QA events never touched reserve cells.
- **Future benchmark**: gate flips READY (frozen threshold semantics +
  v0.2.2 QA verdict), enabling protocol freeze and Stage A benchmarks on
  the same 67-cell universe (53 panel + 14 repair cells, 67 ≤ 96 cap).
- **Integrity cost**: requires honest versioning — v0.2.2 checksummed,
  superseding the Phase J contract text, with the audit trail
  (HISTORICAL_QA_CONSISTENCY_AUDIT, FORENSIC_REPORT, this analysis)
  committed before any readiness re-stamp. All published v0.2 numbers
  remain reproducible under the original contract (no retroactive
  edits).

## Option C — expand the discovery pool under a revised protocol

Change: admit EARLY-tertile candidates currently prefiltered out for the
failed slot (`LE71190372015278EDC00`, cloud_cover 43 % > 0.30; partial-
overlap frames with nominal < 0.90) under a formally revised prefilter.

- **35 repair products**: adds at most 1 substitute scene for the failed
  slot; the existing 34 remain valid.
- **53-cell panel**: no retroactive change, but the pool asymmetry is
  real — panel cells were planned under the 0.30 cloud prefilter; a
  repair cell admitted under a looser prefilter weakens cross-cell
  comparability of the Landsat-temporal track (selection criteria would
  differ between panel and repair cells unless the whole track is
  re-planned under the new prefilter — which re-opens Phase D/E for all
  cells, far beyond scope).
- **Reserve**: unchanged directly; but a re-planned track would touch
  plan provenance for every cell, increasing the chance of procedural
  leakage into sealed-role discussions.
- **Future benchmark**: imports systematically cloudier scenes
  (cloud 0.43 scenes have materially higher zero-valid risk — the very
  failure mode being remediated), degrading the GEODATA temporal track
  it is meant to fix.
- **Verdict**: rejected for v0.2.2. If ever pursued, it must be a
  separately versioned protocol change applied uniformly to the whole
  track, decided with benchmark design, not as a single-slot fix.

## Recommendation

**Option B**, executed as a checksummed v0.2.2 revision with the audit
trail above, then re-run the frozen QA machinery (updated contract file
only) and re-stamp readiness. Options A remains the fallback if the
Owner prefers maximal contract stability; Option C is not recommended
for this remediation.
