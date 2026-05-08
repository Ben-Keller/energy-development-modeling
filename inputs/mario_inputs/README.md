# MARIO Coupling Input Templates

These files are starter templates for connecting Calliope-Africa outputs to MARIO.

How to use:

1. Populate each file with project-specific values.
2. Validate coverage (no missing techs, countries, or cost channels).
3. Keep validated files in this folder (`inputs/mario_inputs/`) as the canonical mapping source.

Core principle:

- Keep all mapping logic in data files, not hardcoded Python.
- Version these files with model assumptions and scenario packs.

## Files

- `country_to_pool.csv`
  - Canonical geographic mapping between Calliope locations and pooled regions.
- `calliope_tech_to_mario_sector.csv`
  - Maps technologies to MARIO sectors and shock channels.
- `calliope_cost_to_mario_account.csv`
  - Maps Calliope cost components to MARIO transaction accounts.
- `capex_sector_split.csv`
  - Splits technology CAPEX across supplying sectors.
- `opex_sector_split.csv`
  - Splits operating expenses and fuel spends across sectors.
- `employment_intensity.csv`
  - Direct/total jobs factors by region/sector.
- `value_added_intensity.csv`
  - Value-added multipliers by region/sector.
- `development_indicator_mapping.csv`
  - Maps model outputs to development indicators (SDG-style or custom).
- `scenario_assumptions.csv`
  - Exogenous assumptions used by coupling runs (price/fx/deflator/etc.).
- `scenario_report_scenarios.csv`
  - Analyst-readable structured scenario target table used by MRIO-direct scenario preparation.
  - This replaces any runtime dependency on narrative scenario documents.

## Seeded placeholder files that still require expert calibration

These files are now fully populated with seeded placeholder values so the pipeline can run cleanly in exploratory mode.
They are still not optional if you want policy-grade development outputs.

1. `employment_intensity.csv`
   - Current repo state: seeded placeholder table with 5 regions x 10 energy-relevant sectors.
   - Fill one row per `(mario_region, mario_sector)` used by the exchange builder.
   - Required columns:
     - `mario_region`
     - `mario_sector`
     - `jobs_per_musd_direct`
     - `jobs_per_musd_total`
     - `reference_year`
     - `source`
     - `notes`
   - Replace all `source=placeholder` rows.
   - `jobs_per_musd_total` must be greater than or equal to `jobs_per_musd_direct`.

2. `value_added_intensity.csv`
   - Current repo state: seeded placeholder table with 5 regions x 10 energy-relevant sectors.
   - Fill one row per `(mario_region, mario_sector)` used by the exchange builder.
   - Required columns:
     - `mario_region`
     - `mario_sector`
     - `gva_per_musd_output`
     - `household_income_per_musd_output`
     - `reference_year`
     - `source`
     - `notes`
   - Replace all `source=placeholder` rows.
   - Values must be expressed per `1 MUSD` of output/shock.

3. `scenario_assumptions.csv`
   - Current repo state: seeded placeholder table covering `baseline` and the active EDIM scenario keys.
   - Used by integrated indicator reporting.
   - Required columns:
     - `assumption_key`
     - `scenario_key`
     - `value`
     - `unit`
     - `effective_year`
     - `source`
     - `notes`
   - Replace all `source=placeholder` rows.
   - Use exact EDIM scenario keys for scenario-specific assumptions, or `baseline` for shared defaults.
   - The runtime currently consumes matched assumptions for indicator reporting, especially `carbon_price`.

4. `development_indicator_mapping.csv`
   - Current repo state: seeded mapping file whose rows are all supported by the current runtime.
   - It still needs expert ownership to decide whether these are the right public-facing indicators.

5. `scenario_report_scenarios.csv`
   - Current repo state: structured extraction of the scenario target assumptions used by the MRIO-direct pathway.
   - Keep this synchronized with `inputs/generated/scenario_report_scenarios.json`.
   - Required columns include:
     - `scenario_id`
     - `geography_code`
     - `scenario_code`
     - `scenario_type`
     - `target_years`
     - `shock_category`
     - `parameter`
     - `target_2030`
     - `target_2050`
   - Update this table directly when scenario assumptions change; do not add narrative source documents as runtime inputs.

## Recommended expert workflow

1. Start from the mapping tables.
   - `calliope_tech_to_mario_sector.csv`
   - `capex_sector_split.csv`
   - `opex_sector_split.csv`

2. Enumerate the `(mario_region, mario_sector)` pairs actually used by those mappings.

3. Populate intensity tables using calibrated evidence.
   - Keep sector names exactly aligned with the MARIO database.
   - Keep region names exactly aligned with the MARIO database.
   - Document source methodology in `notes`.

4. Remove placeholder provenance.
   - Replace `source=placeholder` with the actual source name or citation shorthand.

5. Validate before running final scenarios.
   - The EDIM UI `Strict validation` mode will now fail runs if placeholder rows remain in:
     - `employment_intensity.csv`
     - `value_added_intensity.csv`
     - matched rows in `scenario_assumptions.csv`
   - The EDIM UI `Allow placeholder data` toggle lets exploratory runs proceed with these seeded rows while keeping
     other strict checks active.

## Validation checks

- Every active Calliope technology appears in `calliope_tech_to_mario_sector.csv`.
- Every `costs` class and cost component appears in `calliope_cost_to_mario_account.csv`.
- Shares in `capex_sector_split.csv` and `opex_sector_split.csv` sum to 1 by key group.
- No duplicate key tuples in any table.
- Region and sector names match MARIO database exactly.
- No placeholder rows remain in expert-owned calibration tables for final runs.
