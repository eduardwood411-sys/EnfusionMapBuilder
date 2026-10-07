# Enfusion Map Builder — Technology Stack v0.1

## Scope

Первый MVP: детерминированная генерация синтетического мира по seed.

Pipeline:
Seed + Config -> Terrain -> Coastline -> Hydrology -> Basic Biomes -> WorldModel -> Output

## Python

- Python 3.12
- Project virtual environment: .venv

## Core dependencies

- NumPy — raster arrays and numerical processing
- SciPy — numerical and raster processing utilities
- Pillow — PNG image input/output
- pyfastnoiselite — deterministic procedural noise
- pyflwdir — flow direction, accumulation and hydrology

Exact package versions are stored in requirements-lock.txt.

## Deferred components

The following are intentionally not required for v0.1:

- Landlab — erosion / landscape evolution
- GDAL — GIS and RealWorld pipeline
- GRASS GIS — advanced hydrology and GIS validation
- WhiteboxTools — optional GIS/hydrology backend and validation

These may be integrated later after the minimal procedural pipeline is working.

## Architecture rules

- Core must remain independent of Arma Reforger-specific prefabs and APIs.
- Procedural generation must be reproducible from seed and configuration.
- Existing mature libraries are preferred over custom algorithms.
- Generated Output must be rebuildable from source code and configuration.
- Reforger-specific export belongs in Adapters/ArmaReforger.

## v0.1 exclusions

- Roads
- Settlements
- Buildings
- Asset Resolver
- Final vegetation placement
- Workbench automation
- RealWorld data ingestion
