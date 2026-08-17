# Laboratory 4: Geospatial Data

Reproducible Sentinel-2 workflow for exploratory cyanobacteria monitoring in Lakes Atitlan and
Amatitlan. The package acquires the 22 official scenes, creates georeferenced analytical products,
validates evidence, performs exercises 4-8 offline, and generates a Spanish report for
environmental professionals.

`Lab4.ipynb` is retained as historical work. Its in-memory outputs are **not accepted as evidence**
by this pipeline because the earlier workflow cast reflectance to `UINT16`, did not persist grids or
masks, and dropped the `-1` surface-bloom class from temporal summaries. Use the CLI below as the
canonical implementation.

## Setup

Requirements: Python 3.14 and [uv](https://docs.astral.sh/uv/). `pandoc` and `xelatex` are optional
and only required for PDF generation.

```bash
uv sync --dev
cp .env.example .env
```

Create OAuth client credentials in the Copernicus Data Space Sentinel Hub dashboard, then fill in
`SH_CLIENT_ID` and `SH_CLIENT_SECRET` in `.env`. The file is ignored by Git. Never commit secrets.

## Workflow

Run commands from the repository root.

```bash
# Download all 11 official dates for both lakes and build analytical GeoTIFFs.
uv run lab4 acquire

# Optional focused/restartable downloads.
uv run lab4 acquire --lake atitlan
uv run lab4 acquire --lake amatitlan --date 2026-02-07
uv run lab4 acquire --lake atitlan --date 2025-01-18 --overwrite

# Recreate analytical products offline from already downloaded raw GeoTIFFs.
uv run lab4 process --overwrite

# Exercises 4-8: tables, temporal/spatial figures, correlations, comparison,
# threshold sensitivity, persistence, differences, and exploratory seasonality.
uv run lab4 analyze

# Verify all 22 official scenes, metadata, grids, masks, and usable water pixels.
uv run lab4 validate

# Generate the evidence-driven Spanish Markdown report and optional PDF.
uv run lab4 report
uv run lab4 report --pdf
```

`validate` exits nonzero if any official artifact is missing or structurally invalid. This is
intentional: a partial download must not be presented as a complete laboratory result.

## Scientific Method

### Acquisition and masking

- `config/lakes.json` stores every official date, reported cloud percentage, satellite, bounding
  box, resolution, algorithm source, and analysis threshold from the handout.
- One aligned Sentinel Hub request retrieves the nine reflectance bands needed by the CyanoLakes
  script plus `SCL` and `dataMask`. Reflectance remains `FLOAT32`; no accidental
  reflectance-to-`UINT16` truncation occurs.
- The exact official day is requested using a half-open one-day interval. `leastCC` mosaicking and
  nearest-neighbor resampling make the request deterministic. Request payloads and evalscript
  hashes are persisted next to each raw raster.
- SCL classes for no data, defective pixels, cloud shadow, medium/high cloud, cirrus, and snow are
  excluded. The official WBI logic supplies the water mask.
- The original custom script is documented as an L1C algorithm. This implementation intentionally
  applies its equations to L2A bottom-of-atmosphere reflectance so that SCL masking is available.
  That adaptation is a methodological limitation and results may not be numerically interchangeable
  with the original L1C visualization.

### Analytical representation

The [CyanoLakes custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/cyanobacteria_chla_ndci_l1c/)
is a visualization with two scientifically different branches. This pipeline does not interpret
its display colors as numbers:

- `chlorophyll_proxy` reproduces the script's NDCI polynomial on valid water pixels. It is a proxy
  derived from simulated data, not a laboratory measurement or health standard.
- The unmodified raster retains every polynomial result for auditability. Concentration summaries,
  correlations, and distributions exclude negative values as physically impossible and values at or
  above 500 as outside the documented CyanoLakes training range. No value is silently clamped.
- `surface_bloom` preserves the FAI `> 0.08` classification as a binary layer. The continuous proxy
  is `NaN` there because the official script does not assign a concentration to that branch.
- A high-value pixel is either a retained surface bloom or a finite proxy at/above the configured
  threshold. The default threshold is 20, with sensitivity tables at 10, 20, and 50. These are
  analytical thresholds, not regulatory limits.
- For the lake-level frequency comparison, a bloom date is explicitly defined as a date with at
  least 5% high-value extent. This configurable convention is not a health-alert criterion.
- NDVI and NDWI are calculated only on valid detected-water pixels. Correlations are per pixel for
  each date and pooled by lake, with valid-pair counts reported.
- High-value extent continues to use all valid detected-water pixels as its denominator. Tables
  separately report interpretable proxy coverage, negative estimates, extrapolations above 500, and
  unestimated pixels.

## Outputs

Large/reproducible products are ignored by Git.

| Path | Contents |
| --- | --- |
| `data/raw/<lake>/<date>.tif` | Georeferenced reflectance, SCL, and dataMask source bands |
| `data/raw/<lake>/<date>.json` | Official metadata, request payload, grid, units, and provenance |
| `data/processed/<lake>/<date>.tif` | Proxy, surface bloom, NDVI, NDWI, valid, and water layers |
| `outputs/tables/temporal_summary.csv` | Date-level means, quantiles, coverage, and bloom extent |
| `outputs/tables/critical_dates.csv` | Maximum high-extent date for each lake |
| `outputs/tables/lake_comparison.csv` | Intensity, extent, and bloom-date frequency by lake |
| `outputs/tables/pixel_correlations.csv` | NDVI/NDWI correlations and finite-pixel counts |
| `outputs/tables/threshold_sensitivity.csv` | High-area percentage under each threshold |
| `outputs/tables/exploratory_seasonality.csv` | Small-sample dry/rainy grouping |
| `outputs/tables/spatial_zones.csv` | Coordinate-defined quadrant concentration, persistence, and change |
| `outputs/tables/hotspots_<lake>.tif` | Georeferenced recurrence and persistent-hotspot layers |
| `outputs/figures/` | Temporal, spatial, hotspot, distribution, and difference figures |
| `report/informe.md` | Generated neutral Spanish report source |
| `report/informe.pdf` | Optional generated delivery PDF |

The tracked `report/plantilla.md` is the report source template. If tables do not exist, report
generation produces an explicitly pending document with no fabricated findings or placeholder
figures. After live acquisition, analysis, and validation, it inserts only computed evidence.

## Limitations

- The handout says GeoJSON files are supplied, but none exists in this checkout. The workflow uses
  the official bounding boxes plus spectral water detection. Percentages therefore describe valid
  detected water inside each box, not an authoritative shoreline polygon. Add a sourced lake
  geometry before using area estimates operationally.
- Tile cloud percentages in the handout do not equal local valid coverage. The Amatitlan scene on
  2026-02-07 is explicitly expected to have only about 57.1% valid coverage.
- Optical retrievals are affected by clouds, haze, adjacency to shore, turbidity, mixed pixels,
  bottom reflectance, and atmospheric correction. FAI can also respond to floating vegetation.
- Correlation is not causation. Geography, nutrient loading, urban pressure, temperature, or
  climate require independent measurements and are not inferred from these indices alone.
- Eleven irregular observations per lake over roughly 18 months are insufficient to establish
  robust seasonality. The dry/rainy comparison is exploratory only.
- Satellite signals cannot confirm cyanobacterial species, toxicity, or public-health risk. Field
  sampling remains necessary.

## Quality Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

## Provenance

- Laboratory requirements and official acquisition metadata:
  `docs/Laboratorio 4. Datos Geoespaciales. 2026.pdf`.
- Algorithm: Kravitz, J. and Matthews, M. (2020), *Chlorophyll-a for cyanobacteria blooms from
  Sentinel-2*, CyanoLakes; Sentinel Hub custom scripts repository.
- Imagery attribution for generated products: Contains modified Copernicus Sentinel data processed
  by Sentinel Hub.
