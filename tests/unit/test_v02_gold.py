"""Unit tests for v0.2 GOLD candidate registry rules (Phase K)."""

from __future__ import annotations

import pandas as pd

from spartina.benchmark.v02 import gold


def _row(cid: str, **kw: object) -> dict[str, object]:
    base = {
        "cell_id": cid, "coastal_segment": "EAST_CHINA_SEA",
        "province": "Zhejiang", "agreement_2020": "NONE_PRESENT",
        "area_class": "NONE", "any_positive": False,
        "clean_background": True, "geo15": False, "geo20": False,
        "cmsa20": False, "cmsa21": False, "island": False,
        "max_pos_area_km2": 0.0, "positive_edge_geodata2020": False,
        "center_lon": 120.0, "center_lat": 30.0}
    base.update(kw)
    return base


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_registry_covers_all_types_and_seals_candidate_only() -> None:
    rows = [
        _row("C1", agreement_2020="ALL_THREE_PRESENT", any_positive=True,
             clean_background=False, area_class="MEDIUM"),
        _row("C2", agreement_2020="GEODATA_ONLY", any_positive=True,
             clean_background=False),
        _row("C3"),
        _row("C4", agreement_2020="CMSA_ONLY", any_positive=True,
             clean_background=False, area_class="SMALL"),
        _row("C5", agreement_2020="CMSA_ONLY", any_positive=True,
             clean_background=False, geo15=True),
        _row("C6", agreement_2020="CMSSM_ONLY", any_positive=True,
             clean_background=False),
    ]
    reg = gold.build_registry(_frame(rows), {})
    assert reg["n_candidates"] >= 6
    by_id = {c["cell_id"]: c for c in reg["candidates"]}
    assert "SOURCE_AGREEMENT_POSITIVE" in by_id["C1"]["candidate_types"]
    assert "SOURCE_DISAGREEMENT_POSITIVE" in by_id["C2"]["candidate_types"]
    assert "SOURCE_BACKGROUND" in by_id["C3"]["candidate_types"]
    assert "SMALL_FRAGMENTED_PATCH" in by_id["C4"]["candidate_types"]
    assert "BOUNDARY_SITE" in by_id["C5"]["candidate_types"]
    assert "CONFOUNDER_PRONE" in by_id["C6"]["candidate_types"]
    assert all(c["gold_status"] == gold.GOLD_STATUS for c in
               reg["candidates"])
    assert all(c["high_resolution_evidence_status"] == "NOT_COLLECTED"
               for c in reg["candidates"])
    assert reg["checksum"]


def test_registry_records_pool_deficits_honestly() -> None:
    rows = [_row("C1"), _row("C2")]  # backgrounds only, 2 cells
    reg = gold.build_registry(_frame(rows), {})
    quota = {q["candidate_type"]: q for q in reg["candidate_type_quota"]}
    assert quota["SOURCE_AGREEMENT_POSITIVE"]["pool_size"] == 0
    assert quota["SOURCE_AGREEMENT_POSITIVE"]["selected"] == 0
    deficits = quota["SOURCE_AGREEMENT_POSITIVE"][
        "deficits_max_attainable"]
    assert deficits and "pool 0 < quota" in deficits[0]
    assert quota["SOURCE_BACKGROUND"]["selected"] == 2


def test_registry_caps_at_40_and_checksum_is_deterministic() -> None:
    rows = [
        _row(f"C{i:03d}", agreement_2020="ALL_THREE_PRESENT",
             any_positive=True, clean_background=False,
             area_class="MEDIUM",
             coastal_segment=["EAST_CHINA_SEA", "BOHAI_SEA"][i % 2])
        for i in range(50)]
    reg1 = gold.build_registry(_frame(rows), {})
    reg2 = gold.build_registry(_frame(rows), {})
    assert reg1["checksum"] == reg2["checksum"]
    assert reg1["n_candidates"] <= gold.MAX_CANDIDATE_SITES
    # 10 quota for the agreement type
    quota = {q["candidate_type"]: q for q in reg1["candidate_type_quota"]}
    assert quota["SOURCE_AGREEMENT_POSITIVE"]["selected"] == 10


def test_registry_spreads_round_robin_across_regions() -> None:
    rows = []
    # 9 east cells, 1 bohai cell -- round robin must include bohai in the
    # first two picks instead of taking all east hash-ranked cells.
    for i in range(9):
        rows.append(_row(f"E{i}", agreement_2020="ALL_THREE_PRESENT",
                         any_positive=True, clean_background=False,
                         coastal_segment="EAST_CHINA_SEA"))
    rows.append(_row("B1", agreement_2020="ALL_THREE_PRESENT",
                     any_positive=True, clean_background=False,
                     coastal_segment="BOHAI_SEA"))
    reg = gold.build_registry(_frame(pd.DataFrame(rows)), {})
    quota = next(q for q in reg["candidate_type_quota"]
                 if q["candidate_type"] == "SOURCE_AGREEMENT_POSITIVE")
    chosen = quota["selected_cell_ids"]
    assert "B1" in chosen[:2]
    assert set(quota["regions_used"]) == {"BOHAI_SEA", "EAST_CHINA_SEA"}
