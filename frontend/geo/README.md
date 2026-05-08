# EDIM Spatial Map GeoJSON Requirements

The UI map reads these consolidated GeoJSON files by default:

- `frontend/geo/world_fit.geojson` for fitting the initial map extent
- `frontend/geo/countries.geojson` for country boundaries used by country/subregion rendering

You can override either path before loading the app:

```html
<script>
  window.EDIM_GEOJSON_PATH = "./geo/your_real_model_boundaries.geojson";
  window.EDIM_COUNTRIES_GEOJSON_PATH = "./geo/your_real_country_boundaries.geojson";
</script>
```

## Required model-boundary format

Provide a GeoJSON `FeatureCollection` in EPSG:4326 (longitude/latitude), with each feature as `Polygon` or `MultiPolygon`.

Each feature must include at least one of these identifiers:

- `location_id` (preferred)
- `location`
- `calliope_location`
- `iso3`
- `ISO_A3`
- `id`

The value must exactly match the model `location` key used in exchange outputs, for example `AGO`, `NGA_W`, or `KEN_MTKR`.

Optional properties used as context:

- `mario_region` or `region` for region-level context matching
- `display_name` or `name` for tooltip labels

## Country-boundary format

`countries.geojson` should contain one feature per country or territory. Each country feature must include one ISO-like country identifier in `country_iso3`, `iso3`, `ISO_A3`, `iso3cd`, `location_id`, or `id`.

## Subregion handling

Some model locations are country subregions (`KEN_*`, `NGA_*`, `MOZ_*`). When explicit polygons are not provided, the frontend synthesizes representative subregion areas from known model centroids and clips them inside the parent country boundary from `countries.geojson`.

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
