"""Sensor registry: identity-aware sensor specifications.

The M0 contract for the future sensor-agnostic model: bands are referenced
by **identity** (name, wavelength, sensor, resolution), never by a
hard-coded "channel 4" slot. See
``docs/models/SPARTINAFM_DESIGN.md`` and RQ1/H2 in
``docs/research/HYPOTHESES.md``.

Standard library only at M0. Wavelengths and date ranges are nominal
reference values for the USGS Collection 2 Level-2 / Copernicus
collections named in ``collections.py``; per-scene metadata from the
catalog remains authoritative, and exact per-tile coverage is verified in
M1 (``TODO_VERIFY`` marks where collection specifics must be re-checked
against provider documentation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class Modality(str, Enum):
    """Observation modality of a sensor."""

    OPTICAL = "OPTICAL"
    SAR = "SAR"


@dataclass(frozen=True)
class BandSpec:
    """A single band defined by identity, not by array position."""

    name: str
    wavelength_nm: float | None = None
    resolution_m: float | None = None
    description: str = ""


@dataclass(frozen=True)
class SensorSpec:
    """Full specification of a supported sensor.

    Attributes:
        sensor_name: unique registry key (e.g. ``"landsat8"``).
        platform: human-readable platform name.
        modality: optical or SAR.
        native_resolution_m: nominal native sample distance (highest native
            resolution for sensors with mixed-resolution bands).
        bands: bands available in the analysis-ready collection.
        scale_factor: multiplicative scale to physical units
            (optical Collection-2 surface reflectance: 2.75e-5).
        scale_offset: additive offset (optical Collection-2 SR: -0.2).
        nodata: fill value in the scaled product, if any.
        start_date: nominal first acquisition available (ISO ``YYYY-MM-DD``).
        end_date: nominal last acquisition, or ``None`` if operating.
        qa_bands: names of QA/mask bands in the collection.
        notes: caveats (e.g. SLC-off, mixed band resolutions).
    """

    sensor_name: str
    platform: str
    modality: Modality
    native_resolution_m: float
    bands: tuple[BandSpec, ...]
    scale_factor: float = 1.0
    scale_offset: float = 0.0
    nodata: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    qa_bands: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def __post_init__(self) -> None:
        """Enforce band-identity invariants at construction time."""
        seen: set[str] = set()
        for band in self.bands:
            if band.name in seen:
                raise ValueError(
                    f"Duplicate band {band.name!r} in sensor {self.sensor_name!r}"
                )
            seen.add(band.name)

    def band_names(self) -> tuple[str, ...]:
        """Return all band names in declared order."""
        return tuple(band.name for band in self.bands)

    def get_band(self, band_name: str) -> BandSpec:
        """Look up a band by name.

        Raises:
            KeyError: if the band is not part of this sensor.
        """
        for band in self.bands:
            if band.name == band_name:
                return band
        raise KeyError(f"Band {band_name!r} not defined for sensor {self.sensor_name!r}")

    def wavelength_of(self, band_name: str) -> float | None:
        """Return the nominal centre wavelength (nm) of a band, or ``None``."""
        return self.get_band(band_name).wavelength_nm


# ---------------------------------------------------------------------------
# Built-in specifications (nominal reference values; catalog metadata wins).
# ---------------------------------------------------------------------------

_LANDSAT_C2_SR_SCALE: Final[float] = 2.75e-5
_LANDSAT_C2_SR_OFFSET: Final[float] = -0.2
_LANDSAT_NODATA: Final[int] = -9999
_LANDSAT_QA: Final[tuple[str, ...]] = ("QA_PIXEL", "QA_RADSAT", "ST_QA")

LANDSAT5: Final[SensorSpec] = SensorSpec(
    sensor_name="landsat5",
    platform="Landsat 5 (TM)",
    modality=Modality.OPTICAL,
    native_resolution_m=30.0,
    bands=(
        BandSpec("SR_B1", 485.0, 30.0, "Blue"),
        BandSpec("SR_B2", 560.0, 30.0, "Green"),
        BandSpec("SR_B3", 660.0, 30.0, "Red"),
        BandSpec("SR_B4", 865.0, 30.0, "Near-infrared"),
        BandSpec("SR_B5", 1650.0, 30.0, "Short-wave infrared 1"),
        BandSpec("SR_B7", 2220.0, 30.0, "Short-wave infrared 2"),
        BandSpec("ST_B6", None, 30.0, "Thermal (resampled to 30 m)"),
    ),
    scale_factor=_LANDSAT_C2_SR_SCALE,
    scale_offset=_LANDSAT_C2_SR_OFFSET,
    nodata=_LANDSAT_NODATA,
    start_date="1984-03-16",
    end_date="2013-01-05",
    qa_bands=_LANDSAT_QA,
    notes=(
        "Nominal TM mission range. Collection 2 Level-2; thermal ST_B6 uses "
        "its own scale (see USGS docs); verify per-tile availability in M1."
    ),
)

LANDSAT7: Final[SensorSpec] = SensorSpec(
    sensor_name="landsat7",
    platform="Landsat 7 (ETM+)",
    modality=Modality.OPTICAL,
    native_resolution_m=30.0,
    bands=(
        BandSpec("SR_B1", 483.0, 30.0, "Blue"),
        BandSpec("SR_B2", 560.0, 30.0, "Green"),
        BandSpec("SR_B3", 662.0, 30.0, "Red"),
        BandSpec("SR_B4", 835.0, 30.0, "Near-infrared"),
        BandSpec("SR_B5", 1648.0, 30.0, "Short-wave infrared 1"),
        BandSpec("SR_B7", 2205.0, 30.0, "Short-wave infrared 2"),
        BandSpec("ST_B6", None, 30.0, "Thermal (resampled to 30 m)"),
    ),
    scale_factor=_LANDSAT_C2_SR_SCALE,
    scale_offset=_LANDSAT_C2_SR_OFFSET,
    nodata=_LANDSAT_NODATA,
    start_date="1999-04-15",
    end_date="2022-04-06",
    qa_bands=_LANDSAT_QA,
    notes=(
        "SLC failed on 2003-05-31; post-failure scenes are SLC-off with data "
        "gaps — must be flagged/handled, never silently inpainted."
    ),
)

LANDSAT8: Final[SensorSpec] = SensorSpec(
    sensor_name="landsat8",
    platform="Landsat 8 (OLI/TIRS)",
    modality=Modality.OPTICAL,
    native_resolution_m=30.0,
    bands=(
        BandSpec("SR_B1", 443.0, 30.0, "Coastal/aerosol"),
        BandSpec("SR_B2", 482.0, 30.0, "Blue"),
        BandSpec("SR_B3", 561.0, 30.0, "Green"),
        BandSpec("SR_B4", 655.0, 30.0, "Red"),
        BandSpec("SR_B5", 865.0, 30.0, "Near-infrared"),
        BandSpec("SR_B6", 1609.0, 30.0, "Short-wave infrared 1"),
        BandSpec("SR_B7", 2201.0, 30.0, "Short-wave infrared 2"),
        BandSpec("ST_B10", None, 30.0, "Thermal (resampled to 30 m)"),
    ),
    scale_factor=_LANDSAT_C2_SR_SCALE,
    scale_offset=_LANDSAT_C2_SR_OFFSET,
    nodata=_LANDSAT_NODATA,
    start_date="2013-02-11",
    end_date=None,
    qa_bands=_LANDSAT_QA,
    notes="Collection 2 Level-2; operational WRS-2 acquisitions from 2013-04.",
)

LANDSAT9: Final[SensorSpec] = SensorSpec(
    sensor_name="landsat9",
    platform="Landsat 9 (OLI-2/TIRS-2)",
    modality=Modality.OPTICAL,
    native_resolution_m=30.0,
    bands=(
        BandSpec("SR_B1", 443.0, 30.0, "Coastal/aerosol"),
        BandSpec("SR_B2", 482.0, 30.0, "Blue"),
        BandSpec("SR_B3", 561.0, 30.0, "Green"),
        BandSpec("SR_B4", 655.0, 30.0, "Red"),
        BandSpec("SR_B5", 865.0, 30.0, "Near-infrared"),
        BandSpec("SR_B6", 1609.0, 30.0, "Short-wave infrared 1"),
        BandSpec("SR_B7", 2201.0, 30.0, "Short-wave infrared 2"),
        BandSpec("ST_B10", None, 30.0, "Thermal (resampled to 30 m)"),
    ),
    scale_factor=_LANDSAT_C2_SR_SCALE,
    scale_offset=_LANDSAT_C2_SR_OFFSET,
    nodata=_LANDSAT_NODATA,
    start_date="2021-10-31",
    end_date=None,
    qa_bands=_LANDSAT_QA,
    notes="Collection 2 Level-2; OLI-2 band set equivalent to Landsat 8.",
)

SENTINEL1: Final[SensorSpec] = SensorSpec(
    sensor_name="sentinel1",
    platform="Sentinel-1A/1B (C-SAR, IW GRD)",
    modality=Modality.SAR,
    native_resolution_m=10.0,
    bands=(
        BandSpec("VV", None, 10.0, "C-band SAR, VV co-polarization (sigma0 dB)"),
        BandSpec("VH", None, 10.0, "C-band SAR, VH cross-polarization (sigma0 dB)"),
    ),
    scale_factor=1.0,
    scale_offset=0.0,
    nodata=0,
    start_date="2014-10-01",
    end_date=None,
    qa_bands=(),
    notes=(
        "GRD IW; acquisition orbit (asc/desc) and border-noise/thermal-noise "
        "correction policy must be recorded per product."
    ),
)

SENTINEL2: Final[SensorSpec] = SensorSpec(
    sensor_name="sentinel2",
    platform="Sentinel-2A/2B (MSI)",
    modality=Modality.OPTICAL,
    native_resolution_m=10.0,
    bands=(
        BandSpec("B1", 443.0, 60.0, "Coastal/aerosol"),
        BandSpec("B2", 492.0, 10.0, "Blue"),
        BandSpec("B3", 559.0, 10.0, "Green"),
        BandSpec("B4", 665.0, 10.0, "Red"),
        BandSpec("B5", 704.0, 20.0, "Red-edge 1"),
        BandSpec("B6", 740.0, 20.0, "Red-edge 2"),
        BandSpec("B7", 783.0, 20.0, "Red-edge 3"),
        BandSpec("B8", 833.0, 10.0, "Broad near-infrared"),
        BandSpec("B8A", 864.0, 20.0, "Narrow near-infrared"),
        BandSpec("B9", 943.0, 60.0, "Water vapour"),
        BandSpec("B11", 1610.0, 20.0, "Short-wave infrared 1"),
        BandSpec("B12", 2186.0, 20.0, "Short-wave infrared 2"),
    ),
    scale_factor=1.0,
    scale_offset=0.0,
    nodata=0,
    start_date="2015-06-23",
    end_date=None,
    qa_bands=("SCL", "MSK_CLDPRB"),
    notes=(
        "COPERNICUS/S2_SR_HARMONIZED; reflectance scaled 10000 in GEE "
        "(apply 1e-4 — captured in collection adapter config, not here as a "
        "physical SR offset); mixed native resolutions retained per band."
    ),
)


class SensorRegistry:
    """In-memory registry of :class:`SensorSpec` objects keyed by name."""

    def __init__(self, specs: tuple[SensorSpec, ...] = ()) -> None:
        self._sensors: dict[str, SensorSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: SensorSpec) -> None:
        """Add a sensor; duplicate sensor or band names are rejected."""
        key = spec.sensor_name
        if key in self._sensors:
            raise ValueError(f"Sensor {key!r} is already registered")
        seen: set[str] = set()
        for band in spec.bands:
            if band.name in seen:
                raise ValueError(f"Duplicate band {band.name!r} in sensor {key!r}")
            seen.add(band.name)
        self._sensors[key] = spec

    def get(self, sensor_name: str) -> SensorSpec:
        """Return the spec or raise ``KeyError`` for unknown sensors."""
        try:
            return self._sensors[sensor_name]
        except KeyError:
            raise KeyError(f"Unknown sensor {sensor_name!r}") from None

    def names(self) -> tuple[str, ...]:
        """List registered sensor names."""
        return tuple(sorted(self._sensors))

    def __contains__(self, sensor_name: object) -> bool:
        return sensor_name in self._sensors

    def __len__(self) -> int:
        return len(self._sensors)

    def get_band(self, sensor_name: str, band_name: str) -> BandSpec:
        """Look up a band across a specific sensor."""
        return self.get(sensor_name).get_band(band_name)


def default_registry() -> SensorRegistry:
    """Registry pre-populated with the six M1 target sensors."""
    return SensorRegistry(
        (LANDSAT5, LANDSAT7, LANDSAT8, LANDSAT9, SENTINEL1, SENTINEL2)
    )


__all__ = [
    "BandSpec",
    "Modality",
    "SensorRegistry",
    "SensorSpec",
    "LANDSAT5",
    "LANDSAT7",
    "LANDSAT8",
    "LANDSAT9",
    "SENTINEL1",
    "SENTINEL2",
    "default_registry",
]
