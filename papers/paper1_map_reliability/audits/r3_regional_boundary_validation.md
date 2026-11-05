# R3 — Regional boundary validation

**Date:** 2026-11-05
**Status:** SUPERSEDED IN PART by `audits/r3_geographic_correction.md`;
retained because the R3 brief (Priority 2) required this file.

---

## 1. Separation of perturbation classes

The R2 regional sensitivity experiment moved an x-coordinate cut in EPSG:3410
by ±250 km and ±500 km (`experiments/e5b_boundary_sensitivity.py`,
`results/superseded_e5_longitude_bands/e5b_boundary_sensitivity.csv`).

- **Reasonable perturbations** would be small displacements of a boundary that
  already has geographic meaning (a coastline, a strait, an estuary mouth).
- **Extreme stress tests** would be displacements large enough to merge
  distinct coasts.

The R2 experiment belonged to neither class, because the entity being
perturbed was a meridian line with no geographic meaning. Its apparent
"robustness" (ratio 3.20–3.96× for shifts up to ±250 km, collapsing at
±500 km) measured the stability of an arbitrary segmentation, not the
sensitivity of a geographic classification. That claim is withdrawn.

## 2. What replaces it

The E5d analysis defines regions from IHO-derived marine polygons. Three
definitional uncertainties were identified, and only the first is quantified
here.

| Question | Answer | Evidence |
|---|---|---|
| Do the polygons cover the positive area? | 65.6 % of positive union pixels are directly inside a polygon; 34.42 % are nearest-assigned with max distance 53.97 km | `results/region_definitions_geographic.json` |
| Would admin-1 provinces be a better unit? | No: 86.0 % of positive pixels fall outside the land polygons, because the generalized coastline omits intertidal flats | same JSON, `explored_but_not_primary` |
| How much does the Taiwan Strait grouping matter? | Taiwan Strait contributes 9.33 km² of CMSA's 317.55 km² East China group (2.9 %). Regrouping cannot reverse the Bohai/Yellow–South China contrast | `results/regional_by_marine_polygon_2020.csv` |
| Is there a coastal residual that could bias regions? | 31,201 pixels (7,678 / 22,262 / 1,261 to Bohai/Yellow / East / South). This is reported, not silently absorbed | `region_definitions_geographic.json` |

## 3. Per-polygon decomposition

`results/regional_by_marine_polygon_2020.csv` gives the 2020 mapped area of
each product inside each of the seven named polygons present after clipping:
Bo Hai, Yellow Sea, East China Sea, Hangzhou Bay, Taiwan Strait, South China
Sea, Gulf of Tonkin.

Selected CMSA values (km²): Bo Hai 39.77, Yellow Sea 157.61, East China Sea
137.24, Hangzhou Bay 28.39, Taiwan Strait 9.33, South China Sea 4.78,
Gulf of Tonkin 9.03.

The grouping used in the paper is:

```
Bohai_Yellow   = Bo Hai + Yellow Sea                                  (197.38)
East_China     = East China Sea + Hangzhou Bay + Taiwan Strait        (174.96)
South_China    = South China Sea + Gulf of Tonkin                     (13.81)
```

These sums cover only direct polygon containment. After nearest assignment of
the coastal residual they become 232.16, 317.55 and 19.27 km²
(`results/regional_geographic_2020.csv`). The difference between the two
totals is the residual documented in §2 and must not be read as an
arithmetic inconsistency.

An alternative grouping that moves the Taiwan Strait to the south would shift
9.33 km² (CMSA) into the South China group, whose CMSA area is only
13.81 km². That is a material change *within* the South China group but a
small one relative to the 4.18× contrast, which is driven by the Bohai/Yellow
group's 197.38 km². We therefore report the grouping as a convention and
provide the decomposition rather than asserting a unique answer.

## 4. Conclusion

- The old band-shift sensitivity is retained only as archival evidence.
- The corrected regionalisation has a quantified coastal residual (34.42 %,
  54 km max) and a rejected alternative (admin-1 provinces).
- The Taiwan Strait grouping is the main remaining definitional choice; its
  effect is bounded and documented.
- No claim of "robustness to arbitrary boundary shifts" survives.
