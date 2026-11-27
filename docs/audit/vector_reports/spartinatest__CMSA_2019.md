# Vector report: CMSA_2019.shp

- Driver `ESRI Shapefile`; CRS **EPSG:4326**; features **78**
- Geometry: header `Polygon`, observed `{'Polygon': 78}`
- Bounds: [121.149662, 28.268742, 121.219357, 28.375679]
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

- total **9.2580 km^2** (CRS EPSG:4326)
- min 98.1876 m^2, max 6846749.4 m^2
- geometries < 100.0 m^2 (sliver diagnostics): **5**

## Area-like attribute fields

- `Area_ha`: {"field_sum": 928.85, "field_min": 0.01, "field_max": 686.96, "computed_area_m2_sum": 9257952.177948695, "median_ratio_computed_m2_over_field": 9966.211371962756, "unit_hypothesis": "hectare if ratio~10000", "warning": "hypothesis only; confirm against official field definition / metadata before quoting hectares"}
