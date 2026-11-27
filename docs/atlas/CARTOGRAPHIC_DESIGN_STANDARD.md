# CARTOGRAPHIC_DESIGN_STANDARD

Version: v1.0 (2026-11-27). Binding cartographic standard for every
scientific map of Spartina Earth (Atlas, reports, publications). Bare
colored raster screenshots are **rejected** as final scientific maps.
Reference implementation template:
`engineering/viz/map_template.py` (executable; tested with a synthetic
grid — no fabricated data claims; template renders sample layout only).

## 1. Mandatory elements (all publication/Atlas maps)

1. Real geographic context: coastline + ocean background.
2. Administrative boundaries (national + relevant provincial) where relevant.
3. International borders when the map spans borders (RQ7/Atlas global views).
4. Geographic graticule (labeled degrees).
5. Scale bar (with units; stated datum-consistent projection).
6. North arrow.
7. Legend (class colors + uncertainty symbols).
8. Inset locator (regional/national context box).
9. Data source line (dataset + version + manifest ref).
10. Acquisition year(s) and observation coverage statement.
11. Native spatial resolution statement ("30 m Landsat grid" / "10 m
    Sentinel-2 grid") — never a bare "resolution: 10 m" for 30 m data.
12. Uncertainty representation (per-cell confidence hatch/overlay or
    companion panel; NO_VALID_OBSERVATION rendered distinctly, e.g.
    hatched grey — never as zero/absence).

## 2. Projection and layout

- Analysis rasters stay in their native projected CRS (e.g. EPSG:32651)
  for computation; cartographic rendering reprojects to a suitable
  projected CRS (Albers/UTM zone per extent) — documented per figure.
- Color scheme: sequential viridis-family for continuous quantities;
  ColorBrewer-safe qualitative set for classes (Spartina/recovered
  vegetation/mudflat/water/other); colorblind-safe; uncertainty overlays
  grayscale/alpha.
- NO_VALID_OBSERVATION: distinct neutral hatch; disappearance (Product C)
  uses a distinct negative marker only when evidence criteria met.

## 3. Template contract (engineering/viz/map_template.py)

`render_map(ax, raster, meta, context_layers)` enforces: all 12 elements
checked; missing elements raise `MapStandardError` (the template refuses
to render a non-compliant figure). Elements 2/8 require context layer
files (admin boundaries, coastline) which are PLANNED (not yet
integrated) — until then, template runs in `draft_mode=True` and refuses
`publication=True` rendering. This keeps the standard enforceable rather
than aspirational.

## 4. Static + geospatial deliverables per figure

- Publication static: PDF (vector) + PNG ≥300 dpi.
- Geospatial: GeoTIFF COG per layer + uncertainty layer + coverage layer;
  all with embedded provenance metadata.
- Figure registry: every released figure gets an entry (source rasters'
  SHA-256, model run_id, script SHA) — figures without registry entries
  are not citable project products.
