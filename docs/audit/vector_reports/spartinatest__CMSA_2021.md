# Vector report: CMSA_2021.shp

- Driver `ESRI Shapefile`; CRS **EPSG:4326**; features **105**
- Geometry: header `Polygon`, observed `{'Polygon': 105}`
- Bounds: [121.150353, 28.268989, 121.219568, 28.379467]
- Invalid: **0** ({}); empty: 0; duplicate-geometry feature rows: 0

## Schema

```json
{
  "properties": {
    "Area_ha": "float:6.4",
    "Id": "int32:4",
    "gridcode": "int32:1"
  },
  "geometry": "Polygon"
}
```

## Area (computed, not from the attribute field)

- total **9.4606 km^2** (CRS EPSG:4326)
- min 98.2041 m^2, max 6089454.9 m^2
- geometries < 100.0 m^2 (sliver diagnostics): **8**

## Area-like attribute fields

- `Area_ha`: {"field_sum": 949.2400000000001, "field_min": 0.01, "field_max": 610.99, "computed_area_m2_sum": 9460645.464054173, "median_ratio_computed_m2_over_field": 9963.738038798743, "unit_hypothesis": "hectare if ratio~10000", "warning": "hypothesis only; confirm against official field definition / metadata before quoting hectares"}
