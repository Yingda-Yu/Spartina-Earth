# Vector report: CMSA_2020.shp

- Driver `ESRI Shapefile`; CRS **EPSG:4326**; features **191**
- Geometry: header `Polygon`, observed `{'Polygon': 190, 'MultiPolygon': 1}`
- Bounds: [121.151297, 28.296664, 121.219359, 28.373438]
- Invalid: **0** ({}); empty: 0; duplicate-geometry feature rows: 0

## Schema

```json
{
  "properties": {
    "Area_ha": "float:14.12",
    "Id": "int32:4",
    "gridcode": "int32:1"
  },
  "geometry": "Polygon"
}
```

## Area (computed, not from the attribute field)

- total **4.8295 km^2** (CRS EPSG:4326)
- min 98.1863 m^2, max 1646882.1 m^2
- geometries < 100.0 m^2 (sliver diagnostics): **38**

## Area-like attribute fields

- `Area_ha`: {"field_sum": 484.572975996414, "field_min": 0.01, "field_max": 165.242811221, "computed_area_m2_sum": 4829483.105419645, "median_ratio_computed_m2_over_field": 9958.119583911168, "unit_hypothesis": "hectare if ratio~10000", "warning": "hypothesis only; confirm against official field definition / metadata before quoting hectares"}
