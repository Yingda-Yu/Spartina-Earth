# SUPERSEDED — E5 regional results based on EPSG:3410 x-coordinate bands

**Status:** SUPERSEDED on 2026-11-05. Do not cite these numbers as sea-region results.

## What is wrong

The files here (`regional_agreement_2020.csv`, `e5b_boundary_sensitivity.csv`,
`e5c_iou_bootstrap.csv`, `fig05_regional_iou.*`) split the harmonized EPSG:3410
domain at x = 11,000,000 m and x = 11,500,000 m and labelled the resulting bands:

| Band | x range (m) | Actual longitude range | Label previously used |
|---|---|---|---|
| A | x < 11,000,000 | < 114.24 E | "Bohai/Yellow Sea" |
| B | 11,000,000 – 11,500,000 | 114.24 – 119.42 E | "East China Sea" |
| C | x >= 11,500,000 | > 119.42 E | "South China Sea" |

EPSG:3410 (NSIDC EASE-Grid Global) is a cylindrical equal-area projection whose
x coordinate is a linear function of longitude (96.3 km per degree). The bands
are therefore pure longitude slices, not sea regions. Verified mapping of
reference cities (pyproj EPSG:4326 -> EPSG:3410):

| City | Longitude | x (m) | Band | Actual sea region |
|---|---|---|---|---|
| Beihai (Guangxi) | 109.1 E | 10.506 M | A | South China Sea |
| Haikou (Hainan) | 110.3 E | 10.622 M | A | South China Sea |
| Guangzhou | 113.3 E | 10.911 M | A | South China Sea |
| Xiamen (Fujian) | 118.1 E | 11.373 M | B | Taiwan Strait / East China Sea |
| Tianjin (Bohai) | 117.7 E | 11.335 M | B | Bohai Sea |
| Shanghai | 121.5 E | 11.701 M | C | East China Sea |
| Yancheng (Jiangsu) | 120.2 E | 11.575 M | C | Yellow Sea |
| Qingdao (Shandong) | 120.4 E | 11.595 M | C | Yellow Sea |
| Dalian (Liaoning) | 121.6 E | 11.710 M | C | Bohai / North Yellow Sea |

Consequently the published claim "Bohai/Yellow Sea shows the lowest agreement
while South China Sea shows the highest" was geographically false: band A
contained the south-west coast (Guangxi, Hainan, western Guangdong) and band C
contained Jiangsu, Shanghai, Shandong and Liaoning.

All conclusions in the R2 manuscript that attached sea-region names or
ecological interpretation to these bands are invalid and have been withdrawn.

## What remains valid

The *arithmetic* is reproducible: the numbers below are correct per-region
IoU values **for those longitude bands**. They are kept only as an archived
sensitivity analysis and must be described as "longitude bands", never as
sea regions.

## Replacement

`experiments/e5d_geographic_regions.py` re-derives regions from the
IHO-derived named sea polygons distributed with Natural Earth 1:10m
*geography marine polygons* (v5.1.1, public domain), writes
`results/regional_geographic_2020.csv`,
`results/regional_by_marine_polygon_2020.csv` and
`results/region_definitions_geographic.json`. The 100 m block-bootstrap and
direct contrast inference that replace the band-based bootstrap are in
`experiments/e5e_bootstrap_100m.py`. An earlier attempt to use Natural Earth
admin-1 provinces was abandoned because 86.0 % of positive union pixels fall
outside those land polygons (the coarse coastline omits intertidal flats).

Note that the band numbering above (A/B/C) does not correspond to the
`Bohai_Yellow` / `East_China` / `South_China` names used in the superseded CSV
files, which is exactly the labelling defect this archive documents.

## Provenance of these copies

The copies here are byte-identical to the originals that remained in
`results/` after R2 (`regional_agreement_2020.csv`,
`e5b_boundary_sensitivity.csv`, `e5c_iou_bootstrap.csv`). The originals were
left in place rather than deleted, per AGENTS.md rule 1 (never delete legacy
experiment records); this directory is the canonical reference and is what the
manuscript now points to. The generating scripts
(`e5_regional_heterogeneity.py`, `e5b_boundary_sensitivity.py`,
`e5c_bootstrap_iou.py`) carry a `SUPERSEDED` header and must not be rerun for
manuscript numbers.
