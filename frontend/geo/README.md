# EDIM Spatial Map GeoJSON Requirements

The UI map reads this file by default:

- `frontend/geo/world_fit.geojson`

For location boundaries, it can also use:

- `frontend/geo/countries_manifest.json`
- `frontend/geo/countries_topojson/*.topo.json`

You can override the path before loading the app:

```html
<script>
  window.EDIM_GEOJSON_PATH = "./geo/your_real_boundaries.geojson";
</script>
```

You can also override country topology sources:

```html
<script>
  window.EDIM_COUNTRIES_MANIFEST_PATH = "./geo/countries_manifest.json";
  window.EDIM_COUNTRIES_TOPO_DIR = "./geo/countries_topojson";
</script>
```

## Required format

Provide a GeoJSON `FeatureCollection` in EPSG:4326 (longitude/latitude), with each feature as `Polygon` or `MultiPolygon`.

Each feature must include at least one of these identifiers:

- `location_id` (preferred)
- `location`
- `calliope_location`
- `iso3`
- `ISO_A3`
- `id`

The value must exactly match the model `location` key used in exchange outputs (for example `AGO`, `NGA_W`, `KEN_MTKR`).

Optional properties used as fallback/context:

- `mario_region` or `region` (for region-level fallback matching)
- `display_name` or `name` (tooltip label)

## Subregion handling

Some model locations are country subregions (`KEN_*`, `NGA_*`, `MOZ_*`). When explicit polygons are not provided,
the frontend synthesizes representative subregion areas from the known model centroids and keeps them inside the
parent country boundary from `countries_topojson`.

## Minimum coverage target

For current outputs, include all model locations found in:

- `outputs/runs/<run_id>/exchange/investment_shocks.csv`
- `outputs/runs/<run_id>/exchange/operating_shocks.csv`

Validation command for one run:

```bash
cd /Users/ben/Documents/UNDP/SEH/energy-development-modeling
RUN_ID=efe5c56b

{
  tail -n +2 "outputs/runs/${RUN_ID}/exchange/investment_shocks.csv"
  tail -n +2 "outputs/runs/${RUN_ID}/exchange/operating_shocks.csv"
} | awk -F',' '{print $5}' | sort -u
```
