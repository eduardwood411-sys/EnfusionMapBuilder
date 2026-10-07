# AGENTS.md

Instructions for AI coding agents working on Enfusion Map Builder.

## Project goal

Enfusion Map Builder is a modular system for generating game worlds for Enfusion.

Primary mode: deterministic procedural generation of original synthetic maps.
Secondary mode: reconstruction of real territories from DEM, GIS, OSM and imagery.

Ruhnu is a production map and test case, not the architecture of the generator.

## Main development rule

Do not reinvent mature solutions.

Before implementing a substantial feature:
1. Search for existing reliable solutions.
2. Prefer official Enfusion/Bohemia tools where appropriate.
3. Check mature open-source libraries and GIS tools.
4. Compare integration cost, maintenance, license and portability.
5. Test the best candidate on a small example.
6. Write a custom implementation only when necessary.

Before implementing terrain synthesis algorithms, evaluate an existing terrain backend first. The default production approach is integration with a mature terrain tool or library, not development of a custom high-quality terrain synthesis engine.

Relevant ecosystems include:
- Enfusion Workbench and Arma Reforger tools
- GDAL / OSGeo
- QGIS
- GRASS GIS
- WhiteboxTools
- GeoPandas / Shapely
- NumPy / SciPy
- established procedural terrain and hydrology libraries

## Architecture boundaries

Sources/Procedural
- Generates reproducible synthetic world plans and inputs from seed and parameters.
- Does not imply custom terrain synthesis.

Sources/RealWorld
- Imports and normalizes real-world geographic data.

World Planner
- Defines semantic world intent, broad geographic composition, terrain-zone intent, desired regions and gameplay constraints.
- Derives reproducible planning parameters from explicit seeds and inputs.
- Does not reproduce the functions of a professional terrain synthesis package.

Terrain Backend
- Produces terrain data from World Planner inputs.
- May integrate Gaea, another mature terrain tool or library, a scientific/open-source system, RealWorld DEM input or a minimal test/mock backend.
- Must remain replaceable; Gaea is the current leading production candidate, not a mandatory or permanent dependency.
- Backend-specific logic belongs in an optional backend/integration layer and must not leak into Core.

WorldModel
- Universal internal representation independent of data origin and target game.
- Common representation for terrain from procedural backends and RealWorld sources.

Core
- Terrain: backend-neutral metadata, elevation normalization, height ranges, masks, coordinate/resolution information, validation and WorldModel conversion; not a custom terrain generator
- Hydrology
- Biomes
- Roads
- Settlements
- Vegetation
- AssetResolver
- Validation

Adapters/ArmaReforger
- All Reforger-specific integration belongs here.
- Workbench API
- Enforce Script
- prefab paths
- FG/PG generators
- Reforger terrain/material mappings

Never place Reforger-specific prefab names, resource paths or APIs in Core.

Use semantic Core entities such as PineForest, ResidentialHouse or LocalDirtRoad.
Translate them into concrete game assets only inside a game adapter.

## Determinism

Procedural generation must be reproducible.

- Explicitly pass or store seeds.
- Store generation parameters.
- Avoid hidden global randomness.
- A repeated build with the same inputs should produce the same result where practical.
- Nondeterministic AI output must not be the sole source of critical world geometry.

## Data safety

Never perform destructive bulk operations without explicit approval.

Do not modify or overwrite source GIS data.
Do not modify the existing Ruhnu Workbench project unless explicitly requested.
Do not modify files outside this repository unless the task explicitly requires it.

Generated data must go to designated Output or temporary locations.
Intermediate data must be replaceable.

Before testing bulk processing:
- use a small test dataset;
- use a synthetic test project;
- verify output before expanding the operation.

## Development workflow

Work incrementally.

1. Understand the task.
2. Identify existing solutions.
3. Propose the simplest viable integration.
4. Implement the smallest useful change.
5. Add or update tests.
6. Run tests.
7. Report what changed and any remaining risks.

Do not silently change architecture.
Do not add large dependencies without explaining why they are needed.
Do not add paid services when a suitable free and reliable solution exists.

## MVP priority

Current MVP priority:

seed + parameters
-> world planning
-> evaluated terrain backend
-> backend-neutral terrain data in WorldModel
-> coastline
-> hydrology
-> basic biomes
-> reproducible output

Roads, vegetation, settlements, Asset Resolver and deeper Workbench automation come later.

## Human responsibilities

AI assists with implementation and automation.

Final artistic composition, Level Design decisions, gameplay routes and visual quality remain human-reviewed.

## Documentation

Document important:
- dependencies;
- external tools;
- versions;
- assumptions;
- input/output formats;
- reproducibility requirements;
- known limitations.

Keep README.md and Docs/ consistent with meaningful architectural changes.
