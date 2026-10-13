# Terrain Backend research

Recorded 2026-10-13. Source: user-reported local installation and manual test
results from this research session. These are observations for the tested versions,
not a complete capability or production-license audit.

## Terrain Mixer

- Tested Terrain Mixer **3.1.3**. **Blender 4.5.14 LTS + Terrain Mixer 3.1.3** works.
- **Blender 5.2.2** can load/enable the extension, but Terrain Mixer setup freezes
  in our test. This does not establish that every Blender 5.2.2 setup fails.
- Terrain Mixer is useful primarily as a heightmap compositor/mixer. It did not
  demonstrate a suitable standalone workflow for controlled synthetic macro-world
  generation, so it is **not the current primary Terrain Backend candidate**.
- With this conclusion documented, the large local TerrainMixer working files
  are disposable. No experiment files were deleted or copied into the repository
  as part of this documentation change.

## TerreSculptor 2.0

- **Free/Open Use 2.0.24.083** is installed and usable.
- It supports terrain import plus **Generate, Noisemap, Erosion, Modify and
  Transform** operations. Their suitability for the production workflow still
  requires a full audit.
- **16-bit grayscale PNG import works.** For the 512x512 EMB test heightmap
  representing 8192x8192 m, physical horizontal scale was successfully configured
  with these settings:

| Setting | Tested value |
| --- | --- |
| Units | Centimeters |
| XZ spacing | 1600 |
| Y spacing | 100 |
| Y scale | 800 |

The current EMB test encodes an 800 m physical elevation span. Its normalized
0–100 values are:

| Physical elevation | Normalized value |
| --- | --- |
| -200 m | 0 |
| Sea level: 0 m | 25 |
| +600 m | 100 |

These normalized values are distinct from PNG integer pixel values.
**TerreSculptor's visual world/grid zero must not be treated as EMB sea level.**
The encoding offset must be respected when interpreting imported elevations.

The old **Synthetic_Test_01_PassA** TerreSculptor project was an exploratory
manual test and is obsolete. **Backend_Test_01** is the current relevant
TerreSculptor experiment and **must be preserved for now**.

## Production direction

Do not continue building custom production terrain generation until ready-made
terrain-generation capabilities are fully audited. Use ready-made terrain/backend
functionality wherever it is sufficient; production remains research-first and
within the free toolchain constraint.

MacroLayout work remains useful as research, validation, physical elevation
encoding, deterministic configuration concepts, and possibly a mock/test source.
The existing [cross-archetype study](MacroLayout_Variability_SmokeTest.md) and
[seed study](MacroLayout_Seed_Variability.md) establish prototype capabilities;
they do not establish a custom production terrain engine as the chosen direction.
