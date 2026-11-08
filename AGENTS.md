# AGENTS.md

Practical instructions for Codex and other AI coding agents working on Enfusion Map Builder, aligned with Enfusion Map Builder Guidelines v1.5 and the research-first approach.

## Goal and priorities

Build a high-quality, reproducible, convenient and reusable process for creating game worlds for Enfusion. Success is measured by the resulting worlds and workflow, not the amount of custom code.

- Synthetic is the primary direction: original synthetic worlds. Depending on the chosen workflow, inputs may include a brief / text description, seed and parameters, references, images and masks, AI outputs, and configurations of external generators / terrain tools.
- RealWorld is secondary: reconstruction of real territories. Prefer sources in this order: official current GIS → DEM/orthophoto → OSM/vector → historical/visual references.
- Synthetic and RealWorld may use different pipelines, tools and data representations.
- Ruhnu is a separate RealWorld production/test case; it must not determine Synthetic architecture.
- Gameplay suitability takes priority over purely geological plausibility.
- Final artistic composition, level design, gameplay routes and visual quality require human review.

## Research before implementation

For each substantial feature or automation task:

1. Define the required result, constraints and practical acceptance criteria.
2. Search for existing solutions before designing custom code.
3. Compare eligible free candidates by result quality, maturity, reliability, reproducibility, performance, integration/maintenance effort, automation potential and portability to future games. Assess gameplay suitability as part of result quality.
4. Run a small practical test using a limited dataset or isolated test project. Record inputs, settings, results and limitations.
5. Select the simplest workflow supported by that evidence.
6. Integrate, configure or adapt existing tools.
7. Write custom code only for a confirmed gap or demonstrated bottleneck that suitable existing solutions do not address.

Check relevant options rather than assuming a particular tool or stack:

- Official Bohemia Interactive / Enfusion / Workbench capabilities and documentation.
- Workshop tools, GitHub projects and community workflows.
- Mature terrain tools and established procedural terrain or hydrology libraries.
- QGIS, GDAL / OSGeo, GRASS GIS and WhiteboxTools.
- GeoPandas, Shapely, NumPy and SciPy.
- OSM and other suitable geographic data sources.
- AI, ChatGPT, ComfyUI and other suitable ready-made solutions.

Verify current capabilities and record research sources and dates. Do not treat an earlier candidate assessment as a permanent decision. Explain significant dependencies and tradeoffs before introducing them. Free tools are a mandatory constraint for the current production workflow.

- Eligible options include open-source tools, freeware, Community/Free editions, built-in Enfusion/Workbench capabilities, free Workshop/GitHub solutions and free libraries.
- Before selecting a free version, verify its actual license, commercial-use restrictions, export limits, resolution limits, automation limits, version compatibility and any other restrictions affecting the workflow.
- Paid products may be researched as references or comparison targets, but must not become mandatory production pipeline dependencies unless the user explicitly changes this constraint.
- Do not propose a paid solution as the primary path for a task that must be completed within the current free toolchain.

## Architecture is a hypothesis

Enfusion Map Builder need not be one application or a predetermined set of modules. It may be a collection of configurations, integrations, small scripts, adapters and external tools.

The previous Sources / World Planner / Terrain Backend / WorldModel / Core / Adapters scheme is a working hypothesis. Change it or use only useful parts when research and tests justify that choice. Do not preserve it solely for compatibility with early prototypes.

Do not create WorldModel, Core, Hydrology, Biomes, Roads, Settlements, Vegetation, Asset Resolver or other modules merely because they appeared in the old architecture. Introduce shared representations and abstraction boundaries only when a tested workflow needs them. Document meaningful architectural decisions and their evidence.

No terrain tool, including Gaea, is a mandatory or preselected production backend. Choose candidates after current research and small tests. Do not develop a custom production terrain engine by default.

## Check built-in Reforger tools first

Before writing Reforger automation, investigate and test relevant built-in World Editor / Workbench capabilities, Terrain Tool, Generators, Shape/Spline, Import Objects, SHP/CSV import and Workshop tools.

Use the supported workflow when it meets the requirements. Add scripts or adapters only for demonstrated gaps. If reusable game-independent code is needed, keep concrete Reforger prefab paths, resources and APIs in the relevant integration rather than imposing game-specific assumptions on it. This does not require creating Core or an adapter module in advance.

## Reproducibility and AI

GUI tools, manual intermediate steps and AI are acceptable when they provide a better reproducible workflow. Full automation is not a goal by itself. The goal is sufficient reproducibility of the selected production variant; not every workflow must have a seed.

- Store input provenance, tool versions, configurations and relevant export/import settings. Preserve seeds and parameters wherever the selected tool provides them.
- Avoid hidden global randomness in custom code; repeated runs with the same inputs should produce the same result where practical.
- Document manual steps so another person can repeat the workflow, and retain intermediate artifacts needed to reproduce the result.
- Preserve AI outputs used in production together with available prompts, seeds, settings and model/workflow versions. Record unavailable metadata and reproducibility limits.
- Do not rely on rerunning nondeterministic AI as the sole way to recover critical world geometry. Preserve the accepted artifacts and validate their suitability for production.

## Distribution and terrain data

Maps are free to access. Donations support the author and must
not be required for access or exclusive gameplay content.
Verify Bohemia Interactive rules and third-party licenses.

For heightmap import, record the physical elevation range,
sea level, resolution, orientation and import settings.
Terrain below sea level remains physical terrain.

Previously tested Goldwep MCP operations do not establish
compatibility with every later Reforger Tools version.
LibreTerrain remains a candidate, not a mandatory backend.
## Data safety

- Never perform destructive bulk operations without explicit approval. Before destructive changes, ensure a recoverable Git checkpoint and/or backup covering the affected data; Git alone may not cover large or untracked assets.
- Do not modify or overwrite Source data, including original GIS inputs. Write derived data to designated Output or temporary locations.
- Do not modify the existing Ruhnu Workbench project unless explicitly requested.
- Do not modify files outside this repository unless the task explicitly requires it.
- Start processing tests on a small area or dataset in an isolated test project. Inspect output before expanding the operation.
- Keep disposable intermediates replaceable while preserving accepted production artifacts and the information needed to reproduce them.

## Development stages

A — Audit existing solutions.
B — Small isolated practical checks.
C — End-to-end production test.
D — Minimal working pipeline.
E — Targeted automation of demonstrated bottlenecks.
F — Custom code only for confirmed gaps.
G — Further development based on practical results.

Do not repeat successful tests without a specific reason.
## Documentation

Record research sources and dates, candidate comparisons, small-test results, chosen workflows and reasons for decisions. Document dependencies, external tools and versions, licenses, assumptions, input/output formats, manual steps, reproducibility requirements and known limitations.

Keep README.md as a concise human-facing overview and AGENTS.md as practical agent instructions. Keep relevant Docs/ consistent when the task scope permits; if it does not, report any remaining inconsistency without editing files outside the authorized scope.
