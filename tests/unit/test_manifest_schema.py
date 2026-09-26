"""Tests for the asset manifest schema and stdlib validator."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from spartina.data.manifests import ValidationError, load_schema, validate_asset
from spartina.labels import LabelQuality

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "datasets" / "manifests" / "schema.json"

MINIMAL_ASSET = {
    "asset_id": "scene-example-1",
    "source": "google_earth_engine",
    "provider": "USGS",
    "sensor": "landsat8",
    "product": "LANDSAT/LC08/C02/T1_L2",
    "acquisition_time": "2020-06-01T02:30:00Z",
    "year": 2020,
    "region": "region-A-anonymized",
    "bbox": [121.0, 30.8, 121.2, 31.0],
    "crs": "EPSG:32651",
    "resolution": {"value_m": 30.0, "native": True},
    "bands": ["SR_B2", "SR_B3", "SR_B4", "SR_B5"],
    "label_type": None,
    "label_quality": "UNLABELED",
    "license": "UNKNOWN",
    "permission": "internal-only",
    "local_uri": None,
    "remote_uri": "LANDSAT/LC08/C02/T1_L2",
    "checksum": None,
    "provenance": {
        "chain": [
            {"step": "source_scene", "identifier": "LC08_example", "version": "C02", "notes": None}
        ]
    },
    "status": "cataloged",
    "notes": "M0 test fixture.",
}


def test_schema_file_is_valid_json_with_required_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["required"])
    expected = {
        "asset_id",
        "source",
        "provider",
        "sensor",
        "product",
        "acquisition_time",
        "year",
        "region",
        "bbox",
        "crs",
        "resolution",
        "bands",
        "label_type",
        "label_quality",
        "license",
        "permission",
        "local_uri",
        "remote_uri",
        "checksum",
        "provenance",
        "status",
        "notes",
    }
    assert expected <= required
    assert set(schema["properties"]["label_quality"]["enum"]) == set(LabelQuality.values())


def test_valid_asset_passes() -> None:
    schema = load_schema(SCHEMA_PATH)
    validate_asset(copy.deepcopy(MINIMAL_ASSET), schema)


def test_missing_required_property_fails() -> None:
    asset = copy.deepcopy(MINIMAL_ASSET)
    del asset["checksum"]
    with pytest.raises(ValidationError, match="checksum"):
        validate_asset(asset, load_schema(SCHEMA_PATH))


def test_bad_label_quality_enum_fails() -> None:
    asset = copy.deepcopy(MINIMAL_ASSET)
    asset["label_quality"] = "PLATINUM"
    with pytest.raises(ValidationError, match="label_quality"):
        validate_asset(asset, load_schema(SCHEMA_PATH))


def test_unexpected_property_fails() -> None:
    asset = copy.deepcopy(MINIMAL_ASSET)
    asset["made_up_field"] = 1
    with pytest.raises(ValidationError, match="unexpected properties"):
        validate_asset(asset, load_schema(SCHEMA_PATH))


def test_fake_native_resolution_must_be_declared_honestly() -> None:
    # Schema itself cannot judge resampling honesty, but it forces the flag
    # to exist so 30 m data cannot silently masquerade as native 10 m.
    asset = copy.deepcopy(MINIMAL_ASSET)
    asset["resolution"] = {"value_m": 10.0, "native": False}
    validate_asset(asset, load_schema(SCHEMA_PATH))
