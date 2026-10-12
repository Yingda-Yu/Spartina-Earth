"""Unit tests for v0.2 multi-date acquisition rules (Issue #21 D/E/G)."""

from __future__ import annotations

from spartina.benchmark.v02 import acquisition as acq


def _s2(event_id: str, doy: int, cloud: float = 0.1) -> dict:
    return {"event_id": event_id, "utc": f"2020-{doy:03d}",
            "doy": doy, "cloud_fraction": cloud}


def test_tertile_boundaries() -> None:
    assert acq.tertile_of(260) == "EARLY"
    assert acq.tertile_of(279) == "EARLY"
    assert acq.tertile_of(280) == "MID"
    assert acq.tertile_of(299) == "MID"
    assert acq.tertile_of(300) == "LATE"
    assert acq.tertile_of(320) == "LATE"
    assert acq.tertile_of(259) is None
    assert acq.tertile_of(321) is None


def test_s2_slots_spread_across_three_tertiles() -> None:
    cands = [_s2("E1", 261), _s2("E2", 275, 0.05),
             _s2("M1", 285), _s2("M2", 295, 0.02),
             _s2("L1", 305), _s2("L2", 318, 0.2)]
    calls: list[str] = []

    def evaluate(cand: dict) -> dict:
        calls.append(cand["event_id"])
        return {"fraction": 0.99, "evidence_source": "TEST"}

    slots = acq.select_tertile_slots(
        "C1", 2020, "sentinel2", cands, acq.s2_slot_rank, evaluate)
    by_name = {s["tertile"]: s for s in slots}
    # EARLY rank: cloud asc -> E2 (0.05) before E1 (0.10)
    assert by_name["EARLY"]["event_id"] == "E2"
    # MID rank: M2 (0.02) before M1
    assert by_name["MID"]["event_id"] == "M2"
    # LATE: L1 (0.10) before L2 (0.20)
    assert by_name["LATE"]["event_id"] == "L1"
    assert {s["status"] for s in slots} == {acq.STATUS_ELIGIBLE}
    assert all(s["n_candidates_evaluated"] == 1 for s in slots)


def test_failed_slot_does_not_borrow_dates_and_ledgers_best() -> None:
    cands = [_s2("E1", 265, 0.05), _s2("E2", 270, 0.05),
             _s2("M1", 290)]

    def evaluate(cand: dict) -> dict:
        fraction = {"E1": 0.40, "E2": 0.80, "M1": 0.99}[cand["event_id"]]
        return {"fraction": fraction, "evidence_source": "TEST"}

    slots = acq.select_tertile_slots(
        "C1", 2020, "sentinel2", cands, acq.s2_slot_rank, evaluate)
    by_name = {s["tertile"]: s for s in slots}
    early = by_name["EARLY"]
    assert early["status"] == acq.STATUS_NO_ELIGIBLE
    assert early["event_id"] == ""
    assert early["actual_observed_fraction"] == 0.80
    # E2 (doy 270) is closer to EARLY center 269 than E1 (doy 265).
    assert [e["event_id"] for e in early["evaluated"]] == ["E2", "E1"]
    # MID keeps its own date even though EARLY failed (no borrowing).
    assert by_name["MID"]["event_id"] == "M1"
    assert by_name["LATE"]["status"] == acq.STATUS_NO_SCENE
    assert by_name["LATE"]["evaluated"] == []


def test_landsat_sensor_priority_is_deterministic() -> None:
    cands = [
        {"event_id": "A", "scene_id": "LE07_x", "utc": "u", "doy": 290,
         "cloud_fraction": 0.1, "sensor": "landsat7"},
        {"event_id": "B", "scene_id": "LC08_x", "utc": "u", "doy": 290,
         "cloud_fraction": 0.1, "sensor": "landsat8"},
    ]
    ordered = acq.order_by_tertile(cands, acq.landsat_slot_rank)["MID"]
    assert ordered[0]["scene_id"] == "LC08_x"


def _s1(event_id: str, doy: int, pass_dir: str = "ASC",
        orbit: int = 11) -> acq.S1Candidate:
    return acq.S1Candidate(
        event_id=event_id, scene_id=event_id + "_scene", utc=f"u{doy}",
        doy=doy, pass_direction=pass_dir, relative_orbit=orbit,
        platform="S1A")


def test_pairing_primary_picks_min_gap_passing_candidate() -> None:
    s2 = {"event_id": "S2M", "event_utc": "u", "doy": 290,
          "cell_id": "C1", "year": 2020, "tertile": "MID"}
    # gap-1 candidate fails gate; gap-3 passes -> must keep scanning.
    cands = [_s1("NEAR", 291), _s1("GOOD", 293)]

    def evaluate(d: dict) -> dict:
        return {"fraction": 0.5 if d["event_id"] == "NEAR" else 0.99,
                "s1_floor_check_fraction":
                    0.5 if d["event_id"] == "NEAR" else 0.99,
                "evidence_source": "TEST"}

    rec = acq.pair_s2_event(s2, {"ASC": cands, "DESC": []}, evaluate)
    assert rec["status"] == acq.STATUS_PAIRED
    assert rec["s1_event_id"] == "GOOD"
    assert rec["gap_days"] == 3
    assert rec["pair_token"] == acq.NEAR_SYNC_TOKEN
    assert rec["pass"] == "ASC"
    asc_scan = next(p for p in rec["pass_scans"] if p["pass"] == "ASC")
    assert [e["event_id"] for e in asc_scan["evaluated"]] == ["NEAR",
                                                                "GOOD"]
    assert asc_scan["nearest_primary_gap_days"] == 1


def test_pairing_same_day_token() -> None:
    s2 = {"event_id": "S2M", "event_utc": "u", "doy": 290,
          "cell_id": "C1", "year": 2020, "tertile": "MID"}

    def evaluate(_d: dict) -> dict:
        return {"fraction": 0.99, "s1_floor_check_fraction": 0.99,
                "evidence_source": "TEST"}

    rec = acq.pair_s2_event(s2, {"ASC": [_s1("D0", 290)], "DESC": []},
                            evaluate)
    assert rec["gap_days"] == 0
    assert rec["pair_token"] == acq.SAME_DAY_TOKEN


def test_pairing_sensitivity_tier_and_unavailable() -> None:
    s2 = {"event_id": "S2M", "event_utc": "u", "doy": 290,
          "cell_id": "C1", "year": 2020, "tertile": "MID"}
    # nearest in-window at gap 5 fails; extended at gap 10 passes.
    cands = [_s1("FAIL5", 295), _s1("SENS10", 300)]

    def evaluate(d: dict) -> dict:
        frac = 0.5 if d["event_id"] == "FAIL5" else 0.99
        return {"fraction": frac, "s1_floor_check_fraction": frac,
                "evidence_source": "TEST"}

    rec = acq.pair_s2_event(s2, {"ASC": cands, "DESC": []}, evaluate)
    assert rec["status"] == acq.STATUS_SENSITIVITY
    assert rec["s1_event_id"] == "SENS10"
    assert rec["gap_days"] == 10
    assert rec["best_primary_window_gap_days"] == 5

    # nothing within 14 d passes -> unavailable but optical preserved
    rec2 = acq.pair_s2_event(
        s2, {"ASC": [_s1("FAR", 310)], "DESC": []},
        lambda d: {"fraction": 0.2, "s1_floor_check_fraction": 0.2,
                   "evidence_source": "TEST"})
    assert rec2["status"] == acq.STATUS_UNAVAILABLE
    assert rec2["s1_event_id"] == ""
    assert rec2["best_primary_window_gap_days"] is None


def test_pairing_pass_tiebreak_prefers_asc_then_min_gap() -> None:
    s2 = {"event_id": "S2M", "event_utc": "u", "doy": 290,
          "cell_id": "C1", "year": 2020, "tertile": "MID"}
    def evaluate(_d: dict) -> dict:
        return {"fraction": 0.99, "s1_floor_check_fraction": 0.99,
                "evidence_source": "TEST"}
    rec = acq.pair_s2_event(
        s2, {"ASC": [_s1("A2", 292, "ASC")],
             "DESC": [_s1("D2", 292, "DESC")]}, evaluate)
    assert rec["pass"] == "ASC"
    assert rec["gap_days"] == 2


def test_document_checksum_excludes_volatile_keys() -> None:
    doc1 = {"a": 1, "generated_utc": "t1", "git_commit": "g1"}
    doc2 = {"a": 1, "generated_utc": "t2", "git_commit": "g2"}
    assert acq.document_checksum(doc1) == acq.document_checksum(doc2)
    doc3 = {"a": 2, "generated_utc": "t1"}
    assert acq.document_checksum(doc1) != acq.document_checksum(doc3)


def test_pairing_requires_autumn_primary_window() -> None:
    # S2 at doy 260: an S1 at doy 255 (gap 5) is OUTSIDE the autumn
    # window -> must not become a primary pair even though gap <= 7.
    s2 = {"event_id": "S2E", "event_utc": "u", "doy": 260,
          "cell_id": "C1", "year": 2020, "tertile": "EARLY"}
    cands = [_s1("OUT", 255)]
    rec = acq.pair_s2_event(
        s2, {"ASC": cands, "DESC": []},
        lambda _d: {"fraction": 0.99, "s1_floor_check_fraction": 0.99,
                    "evidence_source": "TEST"})
    # Out-of-window near date may only land in the frozen sensitivity tier.
    assert rec["status"] == acq.STATUS_SENSITIVITY
    assert rec["s1_event_id"] == "OUT"
    scan = rec["pass_scans"][0]["evaluated"][0]
    assert scan["outside_autumn_window"] is True
