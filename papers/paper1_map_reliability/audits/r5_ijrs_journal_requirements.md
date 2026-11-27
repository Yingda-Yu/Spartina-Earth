# R5-02 — IJRS Journal Requirements Audit (Live Retrieval)

**Target journal:** International Journal of Remote Sensing (IJRS), Taylor & Francis
**Retrieved:** 2026-11-08, from the official Taylor & Francis website
**Owner hard requirements:** SCIE indexing; CAS Q3/Q4 preferred; no compulsory
publication charges (subscription route); reasonably fast review.

---

## 1. Verdict on owner hard requirements

| Requirement | Status | Evidence |
|---|---|---|
| SCIE indexing | **PASS** | Journal listed in Science Citation Index Expanded™ (official Abstracting & Indexing list); has a Clarivate Impact Factor (2.6, 2025), which only SCIE/SSCI/AHCI/ESCI journals carry |
| CAS Q3/Q4 | **PASS (Q4)** | CAS 2025 upgraded edition (2025-03 release): major category Earth Sciences (地球科学) **Q4**; minor categories Remote Sensing Q4, Imaging Science & Photographic Technology Q4. Prior editions: 2024-12 edition Q3. Sources: LetPub journal 3875, ablesci.com, justscience.cn (third-party CAS-partition trackers; CAS does not publish an open official list) |
| Subscription route, zero mandatory APC | **PASS** | Official Open Access section: "If you choose not to publish open access in this journal, there is no APC." Instructions for Authors: "There is no submission charge." No page or colour charges are listed for the subscription route |
| Reasonably fast review | **PASS** | Official journal metrics: 4 days average submission→first decision; 57 days average submission→first post-review decision; 14 days acceptance→online publication; 15% acceptance rate |

**No hard requirement fails. Journal-specific submission packaging may proceed,
via the subscription (non-APC) route only.**

---

## 2. Journal identity and metrics (official About page)

- URL: https://www.tandfonline.com/journals/tres20/about-this-journal
- Print ISSN 0143-1161; Online ISSN 1366-5901
- Subscription-based peer-reviewed journal; official journal of the Remote
  Sensing and Photogrammetry Society (RSPSoc); hybrid "Open Select" journal
- Impact Factor 2.6 (2025); 5-year IF 2.8; CiteScore 5.0 (Scopus, Q1 best
  quartile); SNIP 0.657; SJR 0.604; 655K annual downloads
- Single-anonymized peer review policy
- Accepts **original research articles** and review papers — our manuscript
  type (original research) is accepted
- Scope explicitly covers "Remotely sensed data collection, analysis,
  interpretation and display", "Image processing", and "Use of remotely
  sensed data" — multi-source map agreement analysis is in scope
- Editor-in-Chief: Prof. Kevin Tansey (University of Leicester)

## 3. Instructions for Authors (retrieved live, 2026-11-08)

- URL: https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode=tres20
- Page title: "Submit to International Journal of Remote Sensing"

| Item | Requirement |
|---|---|
| Abstract | Unstructured, **≤ 300 words** (current manuscript abstract exceeds this — must be trimmed) |
| Keywords | Not embedded in the body text; entered during submission; no count specified on the instructions page (T&F submission form typically allows up to ~6; enter the most relevant at submission) |
| Manuscript length | **No maximum word/page limit stated** for original research articles; authors must include a word count with the submission |
| Paper structure | Title page; abstract; keywords; main text (introduction, materials and methods, results, discussion); acknowledgments; disclosure of interest statement; references |
| Citation style | **Chicago Author-Date** (guide: https://files.taylorandfrancis.com/tf_chicagoad.pdf; EndNote output style available) — compatible with `natbib` author-year, which the manuscript already uses |
| Figures | High quality: 1200 dpi line art, 600 dpi grayscale, 300 dpi colour at correct size; preferred formats **PS, EPS, TIFF, JPG** (our vector PDFs must be exported to EPS/TIFF for submission) |
| Supplementary material | Published online via Figshare; videos, filesets, audio, or anything supporting the paper |
| Data policy | **"Share Upon Reasonable Request"** data policy; a **Data Availability Statement is required**; open sharing should use a recognized repository |
| Declarations | Funding statement (all sources of financial support); Disclosure of interest ("The authors report no conflict of interest" suggested wording when none); CRediT author roles supported; generative-AI use disclosure statement; authorship criteria (all authors, ≥1 corresponding author with full name, affiliation, country; ORCID encouraged) |
| Submission portal | https://rp.tandfonline.com/submission/create?journalCode=tres |
| Fees | No submission charge; no APC on subscription route; APC applies only if Open Select (gold OA) is chosen — **we will not choose it** |

## 4. Fee summary (subscription route)

- Submission charge: none
- Page charge: none listed
- Colour charge: none listed for the subscription route in current instructions
- APC: none unless the authors opt into Open Select gold open access
- RSPSoc members receive a 50% APC discount if they *choose* gold OA — not
  applicable to the subscription route

## 5. Editorial and review timelines (official metrics, prior six months)

- Submission to first decision (incl. desk rejections): 4 days average
- Submission to first post-review decision: 57 days average
- Acceptance to online publication: 14 days average
- Acceptance rate: 15%
- Review policy: single-anonymized

## 6. Sources

Official (Taylor & Francis):
- About: https://www.tandfonline.com/journals/tres20/about-this-journal
- Instructions for Authors: https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode=tres20
- Chicago Author-Date reference guide: https://files.taylorandfrancis.com/tf_chicagoad.pdf
- Submission portal: https://rp.tandfonline.com/submission/create?journalCode=tres
- Open Select: https://tandfonline.com/openaccess/openselect

CAS partition (third-party trackers of the CAS 2025 upgraded edition):
- LetPub: https://www.letpub.com.cn/index.php?page=journalapp&view=detail&journalid=3875
- ABLESCI: https://www.ablesci.com/journal/detail?id=D4bRLp
- Justscience: https://sci.justscience.cn/details.html?sci=1&id=4932

## 7. Consequences for the manuscript

1. **Abstract must be cut to ≤ 300 words** (currently well above).
2. Keywords trimmed to a submission-form-appropriate set (kept in manuscript
   front matter for the source build; final set entered in the portal).
3. Chicago author-date style matches the current natbib usage; bibliography
   format is acceptable with minor field-standard checks.
4. Figures must be exported as EPS or high-resolution TIFF (300 dpi colour /
   600 dpi grayscale / 1200 dpi line art) for the submission package; the
   PDF/PNG versions remain the in-repo canonical render.
5. A Data Availability Statement is required — the manuscript already has one;
   it must be aligned with the "Share Upon Reasonable Request" policy.
6. A generative-AI use disclosure statement must be added to declarations.
7. CRediT author roles should be prepared (owner input needed for real names).
8. Secondary diagnostics should move to Supplementary Information (published
   via Figshare) to keep the main text focused.
