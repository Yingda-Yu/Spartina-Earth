# Cover Letter — International Journal of Remote Sensing

[Date: TODO_OWNER]

Prof. Kevin Tansey
Editor-in-Chief, International Journal of Remote Sensing

Dear Professor Tansey,

We are submitting our original research article, **"Spatial Agreement and
Regional Uncertainty in Multi-Source Maps of *Spartina alterniflora* along
the Chinese Coast,"** for consideration as a research article in the
*International Journal of Remote Sensing*.

**Scientific problem.** Several independently produced remote sensing products
now map the distribution of the invasive saltmarsh grass *Spartina
alterniflora* along the Chinese coast, and national and provincial ecological
assessments increasingly cite their area statistics as if they were
interchangeable. Yet the spatial agreement among these products had never
been systematically quantified, and national management programmes — including
multi-year eradication campaigns — depend on exactly these maps as baselines.
When two maps report similar national areas but disagree about *where* the
species is, monitoring and eradication decisions can be systematically
misdirected without anyone noticing at the national level.

**What we did.** We harmonized three national products — the 10 m China
Coastal Saltmarsh Atlas (CMSA, 2017–2021 annual vectors), the 30 m GEODATA
presence-only time series (1990–2020), and the sub-meter CM-SSM clump product
(2020, 148,072 patches) — onto a common equal-area grid, and quantified
pairwise spatial agreement (IoU/Dice with spatial block-bootstrap confidence
intervals), national and regional area consistency, and sensitivity to
resolution, rasterization, coastline buffering and geographic-assignment
rules.

**Verified findings.** National mapped areas for 2020 differ by only 14.2%,
but pairwise IoU ranges from 0.54 down to 0.34. The disagreement is
geographically heterogeneous and product-pair dependent: a 4.2× IoU contrast
between the Bohai/Yellow Sea and the South China Sea (95% CI [2.74, 7.51])
for the CMSA–GEODATA pair is robust to every tested assignment policy for
offshore pixels (4.06–4.18× across five policies), while the CMSA–CM-SSM pair
shows no significant regional contrast. Because no product provides a
valid-observation domain and no independent reference data exist, we
explicitly delimit our claims to inter-product agreement rather than
accuracy, and we document why coverage-normalized agreement cannot be
computed from the delivered entities.

**Fit to IJRS.** The study is a remote sensing product-reliability analysis:
it is about interpreting remotely sensed data products, their agreement
structure and the pitfalls of their consumption in operational coastal
monitoring — squarely within the journal's scope of "use of remotely sensed
data" and "remotely sensed data collection, analysis, interpretation and
display." All experiments are reproducible from a versioned public-style
repository record (configuration, seeds and result files are archived; the
harmonized workflow and statistical code are released), and the manuscript
follows the IJRS Instructions for Authors, including the required data
availability statement and a disclosure of interest.

This manuscript is original, has not been published elsewhere, and is not
under consideration by any other journal. All authors have approved the
submission. [TODO_OWNER: confirm/complete author and corresponding-author
details, funding statement, and disclosure of interest.]

We suggest the following potential reviewers: [TODO_OWNER: optional — names,
affiliations and e-mails of 2–4 independent experts].

Thank you for your consideration.

Sincerely,

[TODO_OWNER: corresponding author name]
[TODO_OWNER: affiliation]
[TODO_OWNER: e-mail]
