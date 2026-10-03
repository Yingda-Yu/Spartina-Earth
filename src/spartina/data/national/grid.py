"""Deterministic national 10 km cell grids for coastal China (Issue #14).

Two strategies are defined and compared (instruction section 24):

* ``CHINA_ALBERS`` -- one national equal-area projected lattice
  (China Albers Equal-Area Conic, ESRI:102025 parameters on WGS84).
* ``UTM_ZONE_AWARE`` -- per-zone UTM 10 km lattices for zones 49N-52N,
  which span the mainland coast (~108 E to ~125 E).

"10 km" is a cell *concept*, not a CRS choice (instruction section 25).

This module is deliberately stdlib-only: lattice arithmetic and the
deterministic reversible cell IDs are pure functions.  Shapely/pyproj
geometry assembly lives in :mod:`spartina.data.national.geometry`.

ID grammar (no UUIDs; geometry is recoverable from the ID)::

    CNA10K-R{row:05d}-C{col:05d}
    CNU10K-Z{zone:02d}N-R{row:06d}-C{col:06d}

Both lattices anchor at projected (easting=0, northing=0).  For UTM the
raw projected easting includes the standard 500 km false easting, so a
zone,row,col triple uniquely and reversibly fixes the cell bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

CELL_SIZE_M: Final[int] = 10_000
"""National observation/archive cell edge length (m)."""

CHINA_COASTAL_UTM_ZONES: Final[tuple[int, ...]] = (49, 50, 51, 52)
"""UTM north zones intersected by the China mainland coastline.

Derived from the coastline longitude span (~108 E Beibu Gulf to
~124.5 E Yalu estuary): zone = floor((lon + 180) / 6) + 1.
"""

CHINA_ALBERS_PROJ4: Final[str] = (
    "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 "
    "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
)
"""China Albers Equal-Area Conic parameters (ESRI:102025), WGS84 datum.

Equal-area: every 10 km cell covers exactly 1e8 m**2 in this projection
anywhere in the country.
"""

_ID_PREFIX_AEA: Final[str] = "CNA10K"
_ID_PREFIX_UTM: Final[str] = "CNU10K"


class GridKind(str, Enum):
    """Supported national lattice strategies."""

    CHINA_ALBERS = "CHINA_ALBERS"
    UTM_ZONE_AWARE = "UTM_ZONE_AWARE"


@dataclass(frozen=True)
class CellRef:
    """Reversible lattice index triple."""

    kind: GridKind
    zone: int | None
    row: int
    col: int

    @property
    def cell_id(self) -> str:
        return encode_cell_id(self.kind, self.row, self.col, self.zone)


def utm_epsg(zone: int) -> int:
    """EPSG code for a northern-hemisphere UTM zone."""
    if not 1 <= zone <= 60:
        raise ValueError(f"UTM zone out of range: {zone}")
    return 32600 + zone


def encode_cell_id(kind: GridKind, row: int, col: int, zone: int | None = None) -> str:
    """Encode a lattice index into its deterministic string ID."""
    if kind is GridKind.CHINA_ALBERS:
        if zone is not None:
            raise ValueError("Albers lattice has no zone component")
        return f"{_ID_PREFIX_AEA}-R{row:05d}-C{col:05d}"
    if kind is GridKind.UTM_ZONE_AWARE:
        if zone is None or zone not in CHINA_COASTAL_UTM_ZONES:
            raise ValueError(
                f"UTM lattice requires a coastal zone in "
                f"{CHINA_COASTAL_UTM_ZONES}, got {zone!r}"
            )
        return f"{_ID_PREFIX_UTM}-Z{zone:02d}N-R{row:06d}-C{col:06d}"
    raise ValueError(f"unknown grid kind: {kind!r}")


def parse_cell_id(cell_id: str) -> CellRef:
    """Reverse a cell ID to lattice indices and strategy.

    Raises ``ValueError`` on any malformed or foreign ID so that foreign
    identifiers can never be silently accepted.
    """
    parts = cell_id.split("-")
    if len(parts) == 3 and parts[0] == _ID_PREFIX_AEA:
        row, col = _parse_rc(tuple(parts))
        ref = CellRef(GridKind.CHINA_ALBERS, None, row, col)
    elif len(parts) == 4 and parts[0] == _ID_PREFIX_UTM and parts[1].endswith("N"):
        zone = int(parts[1][1:-1])
        row, col = _parse_rc((parts[2], parts[3]))
        if zone not in CHINA_COASTAL_UTM_ZONES:
            raise ValueError(f"cell ID uses a non-coastal UTM zone: {cell_id}")
        ref = CellRef(GridKind.UTM_ZONE_AWARE, zone, row, col)
    else:
        raise ValueError(f"not a national cell ID: {cell_id!r}")
    if ref.cell_id != cell_id:
        raise ValueError(f"non-canonical cell ID: {cell_id!r} (expected {ref.cell_id})")
    return ref


def _parse_rc(parts: tuple[str, ...]) -> tuple[int, int]:
    row_tok, col_tok = parts[-2], parts[-1]
    if not (row_tok.startswith("R") and col_tok.startswith("C")):
        raise ValueError("cell ID must carry R and C axis tokens")
    return int(row_tok[1:]), int(col_tok[1:])


@dataclass(frozen=True)
class GridSpec:
    """A fixed national lattice specification."""

    kind: GridKind
    cell_size_m: int = CELL_SIZE_M

    def cell_id(self, row: int, col: int, zone: int | None = None) -> str:
        return encode_cell_id(self.kind, row, col, zone)

    def cell_bounds_projected(
        self, row: int, col: int, zone: int | None = None
    ) -> tuple[float, float, float, float]:
        """Return ``(xmin, ymin, xmax, ymax)`` in projected metres.

        For UTM the coordinates are the zone's native projected coordinates
        including the 500 km false easting (lattice anchored at (0, 0)).
        """
        size = self.cell_size_m
        if self.kind is GridKind.UTM_ZONE_AWARE:
            if zone is None or zone not in CHINA_COASTAL_UTM_ZONES:
                raise ValueError("UTM cell bounds require a coastal zone number")
        elif zone is not None:
            raise ValueError("Albers cells carry no zone")
        xmin = col * size
        ymin = row * size
        return (float(xmin), float(ymin), float(xmin + size), float(ymin + size))

    def indices_for_bounds(
        self,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
    ) -> tuple[int, int, int, int]:
        """Return inclusive ``(row_min, row_max, col_min, col_max)`` covering bounds.

        Bounds are in one lattice's projected coordinates.  Floor/ceil are
        used so that boundary-touching cells are retained.
        """
        if xmax <= xmin or ymax <= ymin:
            raise ValueError("bounds must have positive extent")
        size = self.cell_size_m
        col_min = _floor_div(xmin, size)
        col_max = _ceil_div(xmax, size) - 1
        row_min = _floor_div(ymin, size)
        row_max = _ceil_div(ymax, size) - 1
        return row_min, row_max, col_min, col_max


def _floor_div(value: float, size: int) -> int:
    n = int(value // size)
    if n * size > value + 1e-6:  # float guard
        n -= 1
    return n


def _ceil_div(value: float, size: int) -> int:
    n = int(value // size)
    if n * size < value - 1e-6:
        n += 1
    return n


# Static qualitative strategy comparison, kept next to the code so docs and
# implementation cannot drift (instruction section 24).
GRID_STRATEGY_NOTES: Final[dict[str, str]] = {
    "cell_area_distortion": (
        "Albers: every cell is exactly 1e8 m2 nationwide. "
        "UTM: exact inside a zone; cells stay near-square but the zone "
        "lattices are independent and meet only at seams."
    ),
    "shape_distortion": (
        "Albers cells are equal-area everywhere but lose conformality away "
        "from the standard parallels; UTM cells are conformal within ~"
        "+/-3 deg of each zone's central meridian."
    ),
    "adjacency_across_zones": (
        "Albers: one continuous lattice. "
        "UTM: border cells in adjacent zones live in different CRSs and are "
        "not edge-identical in WGS84; joins must be handled explicitly at "
        "zone seams."
    ),
    "id_stability": (
        "Both IDs are deterministic and reversible; UTM IDs additionally "
        "carry the zone, Albers IDs carry none."
    ),
    "spatial_joins": (
        "Albers: single-CRS joins for national vector overlays. "
        "UTM: joins require per-zone reprojection or WGS84 round-tripping."
    ),
    "gee_export_complexity": (
        "Landsat scenes and Sentinel-2 tiles are distributed in native UTM; "
        "UTM-zone cells export without reprojection, Albers cells do not."
    ),
    "historical_raster_compatibility": (
        "The 30 m historical series is stored per province in mixed CRSs "
        "(Krasovsky Albers for 2000; UTM 50N for 2015); CMSA/CM-SSM use UTM. "
        "UTM-zone cells reuse native frames; Albers always reprojects."
    ),
}
