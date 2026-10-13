"""Backend-neutral physical elevation encoding. No terrain or raster generation."""

from dataclasses import dataclass
import json
import math
from numbers import Integral, Real


UINT16_MAX = 65535


def _finite_real(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return value


@dataclass(frozen=True)
class ElevationContract:
    """Linear uint16 mapping with separately declared sea-level metadata.

    All elevations are metres. Sea level may equal either endpoint. Scalar
    conversion preserves array orientation; callers own raster storage and I/O.
    """

    min_elevation_m: float
    sea_level_m: float
    max_elevation_m: float

    def __post_init__(self):
        for name in ("min_elevation_m", "sea_level_m", "max_elevation_m"):
            object.__setattr__(self, name, _finite_real(getattr(self, name), name))
        if not self.min_elevation_m <= self.sea_level_m <= self.max_elevation_m:
            raise ValueError("Sea level must be within the elevation bounds")
        span = self.max_elevation_m - self.min_elevation_m
        if not math.isfinite(span) or span <= 0:
            raise ValueError("Elevation span must be finite and positive")

    @property
    def quantization_step_m(self):
        return (self.max_elevation_m - self.min_elevation_m) / UINT16_MAX

    def encode(self, elevation_m):
        """Metres -> integer in [0, 65535], nearest with ties to even.

        Reject invalid/out-of-range terrain rather than silently clipping it.
        """
        value = _finite_real(elevation_m, "elevation_m")
        if not self.min_elevation_m <= value <= self.max_elevation_m:
            raise ValueError("Elevation is outside the configured bounds")
        normalized = ((value - self.min_elevation_m)
                      / (self.max_elevation_m - self.min_elevation_m))
        return round(normalized * UINT16_MAX)

    def decode(self, height_uint16):
        """Integer uint16 value -> physical metres, including underwater terrain."""
        if (isinstance(height_uint16, bool) or not isinstance(height_uint16, Integral)
                or not 0 <= height_uint16 <= UINT16_MAX):
            raise ValueError("Height must be an integer in [0, 65535]")
        return (self.min_elevation_m + int(height_uint16) / UINT16_MAX
                * (self.max_elevation_m - self.min_elevation_m))

    def metadata(self):
        """Fresh, JSON-compatible encoding metadata, independent of any backend."""
        return {
            "min_elevation_m": self.min_elevation_m,
            "sea_level_m": self.sea_level_m,
            "max_elevation_m": self.max_elevation_m,
            "sea_level_uint16": self.encode(self.sea_level_m),
            "quantization_step_m": self.quantization_step_m,
        }

    def metadata_json(self):
        """Stable serialization without timestamps, paths or backend settings."""
        return json.dumps(self.metadata(), sort_keys=True, indent=2, allow_nan=False) + "\n"
