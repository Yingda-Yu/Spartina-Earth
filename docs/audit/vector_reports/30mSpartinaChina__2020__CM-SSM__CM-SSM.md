# Vector report: CM-SSM.shp

- Driver `ESRI Shapefile`; CRS **EPSG:32650**; features **148072**
- Geometry: header `Polygon`, observed `{'Polygon': 148072}`
- Bounds: [-346085.784611, 2335243.388142, 1017464.956483, 4341555.0]
- Invalid: **2402** ({'Ring Self-intersection': 2402}); empty: 0; duplicate-geometry feature rows: 0

## Schema

```json
{
  "properties": {
    "Id": "int32:6",
    "name": "str:50",
    "area": "float:13.11"
  },
  "geometry": "Polygon"
}
```

## Area (computed, not from the attribute field)

- total **593.7098 km^2** (CRS EPSG:32650)
- min 0.8100 m^2, max 48667459.2 m^2
- geometries < 100.0 m^2 (sliver diagnostics): **100455**

## Area-like attribute fields

- `area`: {"field_sum": 59370.98228275039, "field_min": 8.09994e-05, "field_max": 4866.75, "computed_area_m2_sum": 593709849.716549, "median_ratio_computed_m2_over_field": 9999.999999993423, "unit_hypothesis": "hectare if ratio~10000", "warning": "hypothesis only; confirm against official field definition / metadata before quoting hectares"}

## Breakdown by `name`

{
  "ZJ": 39764,
  "FJ": 28619,
  "SH": 24566,
  "JS": 24180,
  "GX": 12658,
  "SD": 9490,
  "TJ": 6203,
  "GD": 2082,
  "HB": 510
}
