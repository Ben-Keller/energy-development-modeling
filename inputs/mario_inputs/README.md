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

## Validation checks

- Every active Calliope technology appears in `calliope_tech_to_mario_sector.csv`.
- Every `costs` class and cost component appears in `calliope_cost_to_mario_account.csv`.
- Shares in `capex_sector_split.csv` and `opex_sector_split.csv` sum to 1 by key group.
- No duplicate key tuples in any table.
- Region and sector names match MARIO database exactly.
