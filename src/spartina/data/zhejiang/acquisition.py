"""Acquisition-group (ObservationEvent) model + cell-level QA simulation.

M2.1a2 (Issue #12). Replaces the inappropriate bay x individual-scene
gate with a physically coherent event model:

* Sentinel-2: adjacent MGRS tiles are grouped ONLY when they share one
  compatible acquisition event. Primary key is the real GEE
  ``DATATAKE_IDENTIFIER``; if that property is unavailable for a scene the
  deterministic fallback (same spacecraft + same UTC calendar date + same
  relative orbit) is used and the row is marked FALLBACK_DATATAKE_MISSING.
* Landsat: one scene per cell when it covers the cell; same-date adjacent
  WRS path/row scenes (same sensor) may form one same-overpass group.
* Sentinel-1: platform / pass / relative orbit / mode / polarization /
  date must all match; ascending and descending are never mixed.

Cross-date "mosaics" are structurally impossible: every grouping key
contains the UTC date, and group construction asserts it.

This module is metadata/geometry only -- no Earth Engine calls, no
pixels, and cell-level cloud statistics use member-scene metadata (the
real SCL pixel QA stays in M2.1b).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep

from spartina.data.gee.selection import canonical_fingerprint
from spartina.data.zhejiang.cells import RELEVANT, CellRecord
from spartina.data.zhejiang.census import parse_utc

GROUP_ID_PREFIX: str = "AG"

DATATAKE_PRESENT: str = "DATATAKE_IDENTIFIER_PRESENT"
DATATAKE_FALLBACK: str = "FALLBACK_SAME_DATE_REL_ORBIT"
DATATAKE_MISSING: str = "DATATAKE_IDENTIFIER_MISSING_IN_GEE"

S2_GROUP_RULE: str = "same_datatake_identifier"
S2_FALLBACK_RULE: str = "same_spacecraft_date_relative_orbit"
LANDSAT_GROUP_RULE: str = "same_sensor_utc_date_adjacent_wrs_manhattan1"
S1_GROUP_RULE: str = "same_platform_pass_relorbit_mode_pol_date"
SINGLE_SCENE_RULE: str = "single_scene"

QA_BASIS: str = (
    "CELLxEVENT_GEOMETRY_COVERAGE_PLUS_MEMBER_SCENE_CLOUD_METADATA;"
    "PIXEL_SCL_QA_DEFERRED_TO_M21B"
)

CLOUD_GATE_PASS: str = "PASS"
CLOUD_GATE_FAIL: str = "FAIL_SCENE_CLOUD"
CLOUD_GATE_NA: str = "NOT_APPLICABLE_SAR"
CLOUD_GATE_MISSING: str = "FAIL_CLOUD_METADATA_MISSING"

# Frame-geometry regimes. Landsat 7 kept acquiring nominal science images
# until 2024-01-19 after the April 2022 disposal burns lowered its orbit by
# ~8 km ("Extended Science Mission"); those post-burn scenes no longer
# follow the nominal WRS ground track, so nominal WRS frame polygons are
# only an approximation for them. Source: USGS EROS Landsat 7 C2 L1 page
# (usgs.gov, retrieved 2026-10-02).
L7_EXTENDED_MISSION_START: str = "2022-04-01"
GEOM_NOMINAL_WRS: str = "NOMINAL_WRS_FRAME"
GEOM_L7_EXTENDED: str = (
    "L7_EXTENDED_SCIENCE_MISSION_LOWER_ORBIT_WRS_APPROXIMATION")
GEOM_NOMINAL_MGRS: str = "NOMINAL_MGRS_TILE"
GEOM_S1_REPRESENTATIVE: str = "REPRESENTATIVE_FRAME_PER_TRACK_VARIES"

# ---------------------------------------------------------------------------
# Group data model
# ---------------------------------------------------------------------------
@dataclass
class AcquisitionGroup:
    group_id: str
    sensor: str
    event_date: str
    event_utc_start: str
    event_utc_end: str
    n_scenes: int
    spacecraft: str
    orbit_direction: str
    relative_orbit_numbers: str
    tile_refs: str
    instrument_mode: str
    polarizations: str
    processing_baselines: str
    datatake_identifiers: str
    datatake_status: str
    grouping_rule: str
    slc_statuses: str
    geometry_regime: str
    member_scene_ids: list[str] = field(default_factory=list)
    footprint_frame_keys: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "sensor": self.sensor,
            "event_date": self.event_date,
            "event_utc_start": self.event_utc_start,
            "event_utc_end": self.event_utc_end,
            "n_scenes": self.n_scenes,
            "spacecraft": self.spacecraft,
            "orbit_direction": self.orbit_direction,
            "relative_orbit_numbers": self.relative_orbit_numbers,
            "tile_refs": self.tile_refs,
            "instrument_mode": self.instrument_mode,
            "polarizations": self.polarizations,
            "processing_baselines": self.processing_baselines,
            "datatake_identifiers": self.datatake_identifiers,
            "datatake_status": self.datatake_status,
            "grouping_rule": self.grouping_rule,
            "slc_statuses": self.slc_statuses,
            "geometry_regime": self.geometry_regime,
            "member_scene_ids": "|".join(self.member_scene_ids),
            "footprint_frame_keys": "|".join(self.footprint_frame_keys),
            "group_fingerprint": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        payload = {
            "sensor": self.sensor,
            "event_utc_start": self.event_utc_start,
            "spacecraft": sorted(self.spacecraft.split("|")) if self.spacecraft else [],
            "orbit_direction": self.orbit_direction,
            "relative_orbit_numbers": (
                sorted(self.relative_orbit_numbers.split("|"))
                if self.relative_orbit_numbers else []),
            "instrument_mode": self.instrument_mode,
            "polarizations": self.polarizations,
            "member_scene_ids": sorted(self.member_scene_ids),
            "footprint_frame_keys": sorted(self.footprint_frame_keys),
        }
        return canonical_fingerprint(payload)


ACQUISITION_GROUP_COLUMNS: tuple[str, ...] = (
    "group_id",
    "sensor",
    "event_date",
    "event_utc_start",
    "event_utc_end",
    "n_scenes",
    "spacecraft",
    "orbit_direction",
    "relative_orbit_numbers",
    "tile_refs",
    "instrument_mode",
    "polarizations",
    "processing_baselines",
    "datatake_identifiers",
    "datatake_status",
    "grouping_rule",
    "slc_statuses",
    "geometry_regime",
    "member_scene_ids",
    "footprint_frame_keys",
    "group_fingerprint",
)


# ---------------------------------------------------------------------------
# Frame keys (a frame is the fixed geometry shared by same-ref scenes)
# ---------------------------------------------------------------------------
def frame_key(scene: dict[str, Any]) -> str:
    sensor = scene["sensor"]
    if sensor == "sentinel2":
        return f"MGRS:{scene['tile_ref']}"
    if sensor.startswith("landsat"):
        return f"WRS:{scene['tile_ref']}"
    if sensor == "sentinel1":
        return (f"S1:{scene.get('orbit_direction')}:"
                f"{_num(scene.get('relative_orbit_number'))}")
    raise ValueError(f"unknown sensor {sensor}")


def _num(value: Any) -> str:
    if value is None or value == "":
        return "UNKNOWN"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _sorted_join(values: Any) -> str:
    out = sorted({str(v) for v in values if v not in (None, "", "nan")})
    return "|".join(out)


# ---------------------------------------------------------------------------
# Scene de-duplication: one physical scene may intersect several bay
# envelopes and therefore appear multiple times in the census table.
# ---------------------------------------------------------------------------
def dedupe_scenes(scenes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        sid = scene["scene_id"]
        if sid not in unique:
            unique[sid] = dict(scene)
    return unique


# ---------------------------------------------------------------------------
# Sentinel-2 grouping
# ---------------------------------------------------------------------------
def _s2_key(scene: dict[str, Any]) -> tuple[Any, ...]:
    datatake = scene.get("datatake_identifier")
    date = scene["acquisition_utc"][:10]
    if datatake:
        return ("DT", str(datatake))
    return ("FB", str(scene.get("spacecraft")), date,
            _num(scene.get("relative_orbit_number")))


def _wrs_adjacent(ref_a: str, ref_b: str) -> bool:
    pa_s, ra_s = ref_a.split("/")
    pb_s, rb_s = ref_b.split("/")
    return abs(int(pa_s) - int(pb_s)) + abs(int(ra_s) - int(rb_s)) == 1


# ---------------------------------------------------------------------------
# Core grouping
# ---------------------------------------------------------------------------
def group_scenes(scenes: list[dict[str, Any]]) -> list[AcquisitionGroup]:
    """Group physical (de-duplicated) scenes into observation events."""
    unique = dedupe_scenes(scenes)
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for scene in unique.values():
        buckets[_group_bucket(scene)].append(scene)

    groups: list[AcquisitionGroup] = []
    for key, members in buckets.items():
        if key[0] == "landsat":
            for component in _split_wrs_components(members):
                groups.append(_build_group(component))
        else:
            groups.append(_build_group(members))
    groups.sort(key=lambda g: (g.event_utc_start, g.sensor, g.group_id))
    return groups


def _split_wrs_components(
    members: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split one (sensor, date) bucket into connected WRS chains."""
    refs = sorted({m["tile_ref"] for m in members})
    if len(refs) <= 1:
        return [members]
    parent = {r: r for r in refs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if _wrs_adjacent(a, b):
                parent[find(a)] = find(b)
    components: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in members:
        components[find(m["tile_ref"])].append(m)
    return list(components.values())


def _group_bucket(scene: dict[str, Any]) -> tuple[Any, ...]:
    sensor = scene["sensor"]
    date = scene["acquisition_utc"][:10]
    if sensor == "sentinel2":
        key = _s2_key(scene)
        return ("s2", *key)
    if sensor == "sentinel1":
        return (
            "s1", date, str(scene.get("spacecraft")),
            str(scene.get("orbit_direction")),
            _num(scene.get("relative_orbit_number")),
            str(scene.get("instrument_mode")),
            str(scene.get("polarizations")),
        )
    # Landsat: per-date per-sensor clusters of WRS-adjacent scenes.
    return ("landsat", sensor, date)


def _build_group(members: list[dict[str, Any]]) -> AcquisitionGroup:
    sensor = members[0]["sensor"]
    dates = {m["acquisition_utc"][:10] for m in members}
    if len(dates) != 1:
        raise AssertionError(
            f"cross-date grouping attempted for {sensor}: {sorted(dates)}")
    event_date = sorted(dates)[0]

    if sensor == "sentinel2":
        rule, status = _s2_rule_status(members)
    elif sensor == "sentinel1":
        rule, status = S1_GROUP_RULE, ""
    else:
        rule, status = _landsat_rule_status(members)

    if sensor == "sentinel2":
        regime = GEOM_NOMINAL_MGRS
    elif sensor == "sentinel1":
        regime = GEOM_S1_REPRESENTATIVE
    elif sensor == "landsat7" and event_date >= L7_EXTENDED_MISSION_START:
        regime = GEOM_L7_EXTENDED
    else:
        regime = GEOM_NOMINAL_WRS

    times = sorted(m["acquisition_utc"] for m in members)
    sids = sorted(m["scene_id"] for m in members)
    frames = sorted({frame_key(m) for m in members})

    g = AcquisitionGroup(
        group_id="",
        sensor=sensor,
        event_date=event_date,
        event_utc_start=times[0],
        event_utc_end=times[-1],
        n_scenes=len(members),
        spacecraft=_sorted_join(m.get("spacecraft") for m in members),
        orbit_direction=_sorted_join(
            m.get("orbit_direction") for m in members),
        relative_orbit_numbers=_sorted_join(
            _num(m.get("relative_orbit_number")) for m in members),
        tile_refs=_sorted_join(m.get("tile_ref") for m in members),
        instrument_mode=_sorted_join(
            m.get("instrument_mode") for m in members),
        polarizations=_sorted_join(
            m.get("polarizations") for m in members),
        processing_baselines=_sorted_join(
            m.get("processing_baseline") for m in members),
        datatake_identifiers=_sorted_join(
            m.get("datatake_identifier") for m in members),
        datatake_status=status,
        grouping_rule=rule if len(members) > 1 else SINGLE_SCENE_RULE,
        slc_statuses=_sorted_join(m.get("slc_status") for m in members
                                  if m.get("slc_status") not in (None, "")),
        geometry_regime=regime,
        member_scene_ids=sids,
        footprint_frame_keys=frames,
    )
    g.group_id = f"{GROUP_ID_PREFIX}_{g.fingerprint()[:16]}"
    return g


def _s2_rule_status(
    members: list[dict[str, Any]],
) -> tuple[str, str]:
    datatakes = {m.get("datatake_identifier") for m in members}
    datatakes.discard(None)
    datatakes.discard("")
    spacecraft = {m.get("spacecraft") for m in members}
    relorbits = {_num(m.get("relative_orbit_number")) for m in members}
    if datatakes:
        if len(datatakes) != 1 or len(spacecraft) != 1 or len(relorbits) != 1:
            raise AssertionError(
                "incompatible scenes forced into one S2 datatake group")
        return S2_GROUP_RULE, DATATAKE_PRESENT
    return S2_FALLBACK_RULE, DATATAKE_FALLBACK


def _landsat_rule_status(
    members: list[dict[str, Any]],
) -> tuple[str, str]:
    """Validate same-overpass compatibility for multi-scene landsat groups."""
    if len(members) == 1:
        return SINGLE_SCENE_RULE, ""
    sensors = {m["sensor"] for m in members}
    if len(sensors) != 1:
        raise AssertionError("mixed-sensor landsat grouping")
    slc = {m.get("slc_status") for m in members}
    slc.discard(None)
    slc.discard("")
    if len(slc) > 1:
        # pre/post SLC failure cannot happen on one UTC date; guard anyway
        raise AssertionError("mixed SLC status in same-date landsat group")
    refs = sorted({m["tile_ref"] for m in members})
    # Connected chain, not a clique: a same-overpass cluster may span three
    # rows (e.g. 118/039 + 118/040 + 118/041 observed in the real census).
    parent = {r: r for r in refs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if _wrs_adjacent(a, b):
                parent[find(a)] = find(b)
    if len({find(r) for r in refs}) != 1:
        raise AssertionError(
            f"non-connected WRS frames in one overpass: {refs}")
    return LANDSAT_GROUP_RULE, ""


# ---------------------------------------------------------------------------
# Cell x group QA simulation (offline, geometry + metadata only)
# ---------------------------------------------------------------------------
CELL_OBSERVATION_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "bay_id",
    "cell_size_m",
    "group_id",
    "sensor",
    "year",
    "event_date",
    "day_of_year",
    "n_member_scenes",
    "coverage_fraction",
    "member_scene_cloud_max",
    "cloud_gate",
    "coverage_gate",
    "window_ids",
    "window_layer",
    "quality_pass",
    "geometry_regime",
    "qa_thresholds",
    "qa_basis",
)


def group_footprint(
    group: AcquisitionGroup,
    frames: dict[str, BaseGeometry],
) -> BaseGeometry:
    geoms = [frames[k] for k in group.footprint_frame_keys if k in frames]
    if not geoms:
        raise KeyError(
            f"no frame footprint for {group.group_id} "
            f"{group.footprint_frame_keys}")
    return unary_union(geoms)


def windows_from_scene(
    doy: int | None,
    windows: list[dict[str, Any]],
) -> str:
    if doy is None:
        return ""
    hits = [
        w["id"] for w in windows
        if int(w["doy_start"]) <= doy <= int(w["doy_end"])
    ]
    return "|".join(hits)


def simulate_cell_observations(
    cells: list[CellRecord],
    groups: list[AcquisitionGroup],
    frames: dict[str, BaseGeometry],
    scenes_by_id: dict[str, dict[str, Any]],
    windows: list[dict[str, Any]],
    *,
    coverage_min: float,
    scene_cloud_max: float,
) -> list[dict[str, Any]]:
    """One QA row per cell x intersecting group.

    Coverage is group-footprint coverage of the fixed cell (>= 0.99 gate).
    For optical sensors every member scene contributing geometry must pass
    the (unchanged) scene-level cloud threshold; S1 has no cloud gate.
    """
    cell_geoms: dict[str, BaseGeometry] = {}
    from spartina.data.zhejiang.cells import cell_polygon, grid_spec

    for cell in cells:
        cell_geoms[cell.cell_id] = cell_polygon(
            grid_spec(cell.cell_size_m), cell.index_east, cell.index_north)

    # bucket cells by size for STRtree-free linear scan (few hundred cells)
    rows: list[dict[str, Any]] = []
    thresholds = f"coverage>={coverage_min};scene_cloud<={scene_cloud_max}"
    for group in groups:
        footprint = group_footprint(group, frames)
        fp_prep = prep(footprint)
        member_clouds = [
            scenes_by_id[sid].get("scene_cloud_fraction")
            for sid in group.member_scene_ids
            if sid in scenes_by_id
        ]
        clouds = [c for c in member_clouds
                  if isinstance(c, int | float)]
        cloud_max = max(clouds) if clouds else None
        if group.sensor == "sentinel1":
            cloud_gate = CLOUD_GATE_NA
        elif cloud_max is None:
            cloud_gate = CLOUD_GATE_MISSING
        elif cloud_max <= scene_cloud_max:
            cloud_gate = CLOUD_GATE_PASS
        else:
            cloud_gate = CLOUD_GATE_FAIL

        event_dt = parse_utc(group.event_utc_start)
        doy = event_dt.timetuple().tm_yday if event_dt else None
        window_ids = windows_from_scene(doy, windows)
        for cell in cells:
            geom = cell_geoms[cell.cell_id]
            if not fp_prep.intersects(geom):
                continue
            coverage = float(
                geom.intersection(footprint).area / geom.area)
            coverage_gate = coverage >= coverage_min
            quality = bool(
                coverage_gate
                and cloud_gate in (CLOUD_GATE_PASS, CLOUD_GATE_NA))
            rows.append({
                "cell_id": cell.cell_id,
                "bay_id": cell.bay_id,
                "cell_size_m": cell.cell_size_m,
                "group_id": group.group_id,
                "sensor": group.sensor,
                "year": int(group.event_date[:4]),
                "event_date": group.event_date,
                "day_of_year": doy,
                "n_member_scenes": group.n_scenes,
                "coverage_fraction": round(coverage, 6),
                "member_scene_cloud_max": (
                    round(cloud_max, 6) if cloud_max is not None else None),
                "cloud_gate": cloud_gate,
                "coverage_gate": bool(coverage_gate),
                "window_ids": window_ids,
                "window_layer": "|".join(sorted({
                    w.get("layer", "season") for w in windows
                    if w["id"] in (window_ids.split("|") if window_ids else [])
                })),
                "quality_pass": quality,
                "geometry_regime": group.geometry_regime,
                "qa_thresholds": thresholds,
                "qa_basis": QA_BASIS,
            })
    rows.sort(key=lambda r: (
        r["cell_size_m"], r["bay_id"], r["year"], r["sensor"],
        r["event_date"], r["cell_id"]))
    return rows


def coastal_cells(records: list[CellRecord]) -> list[CellRecord]:
    return [r for r in records if r.coastal_relevance == RELEVANT]
