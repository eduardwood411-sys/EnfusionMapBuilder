# Terrain data contract

Backend-neutral salvage recorded 2026-10-13. Reviewed Git history and
`generate.py`, `test_macro_layout.py`, and `Synthetic_Test_01_Macro_Elevation.md`
at experiment commit `4f6ec3a00c4a8d1440ae79d1993cd31f5dfbe0d8`. This document,
`Core/Terrain/elevation.py` and its focused tests are self-contained on main;
the experimental branch is not needed to use them.

## Physical elevation and encoding

Declare `min_elevation_m`, `sea_level_m`, and `max_elevation_m` in metres. Limits
must be finite, with a finite positive span and sea level within the bounds.
The example -200 / 0 / +600 m is a test contract, not a mandatory backend range.

For physical elevation `z`, minimum `a` and maximum `b`:

```text
uint16 = round((z - a) / (b - a) * 65535)
metres = a + uint16 / 65535 * (b - a)
```

Rounding is nearest, with ties to even. For the example, -200 m maps to 0,
0 m maps to 16384, and +600 m maps to 65535. The step is approximately
0.0122072 m; encoded sea level decodes to approximately +0.0030518 m.
Physical round-trip error is at most half a step, subject to floating-point
precision. An encoded threshold is quantized; retain exact sea-level metadata.

The standard-library utility validates scalar values and rejects nonfinite,
out-of-bounds, boolean and nonnumeric inputs. Decoding requires integer values
in [0, 65535]; it never casts fractional values or wraps invalid integers.
Unlike the prototype, encoding rejects out-of-range terrain rather than clipping.
Returned heights are Python integers valid for uint16 storage, not typed raster
buffers. Raster dimensions, orientation, pixel spacing, file I/O and backend
import/export settings remain the caller's responsibility. Conversion never
flips or rearranges samples. Store encoding metadata alongside authoritative
16-bit data; an 8-bit preview is for viewing only.

```python
from Core.Terrain.elevation import ElevationContract

contract = ElevationContract(-200, 0, 600)
height = contract.encode(-80)  # underwater terrain remains ordinary terrain
metres = contract.decode(height)
metadata_json = contract.metadata_json()
```

Metadata serialization is deterministic and records the three physical fields,
sea-level uint16 value and quantization step. No timestamps or backend parameters
are introduced. Apply scalar conversion to samples in their existing order;
no NumPy, Pillow or new dependencies are required.

## Water semantics and scope

Terrain continues below water. Sea level describes a water surface; it is not
nodata, a flat seabed, or a reason to zero ocean samples. Future inland water
annotations may declare their own `surface_elevation_m`, separate from both sea
level and terrain elevation. Lake bottoms remain physical terrain. This contract
does not infer wet regions, connectivity, water meshes, hydrology or bathymetry.

Only encoding mathematics, physical/water semantics, deterministic encoding
metadata and focused validation were retained. No MacroLayout generator,
composition primitives, distance-based shelf algorithm, seed sampler, archetype
fixtures, previews, smoke-study projects or historical MacroLayout documents
were copied. External Terrain Backends remain responsible for terrain creation
and refinement; see [Terrain Backend research](Terrain_Backend_Research.md).

Run from the repository root:

```powershell
python -m unittest discover -s Tests -v
git diff --check
```
