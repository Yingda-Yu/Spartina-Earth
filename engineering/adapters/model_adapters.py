"""Model adapter interfaces for SpartinaShift (BENCHMARK_NEXT_STAGE_PLAN §2,
FOUNDATION_MODEL_COMPARISON.md).

Interfaces only — no pretrained weights, no fabricated implementations.
Concrete adapters (Prithvi-EO-2.0, SatMAE++, AnySat) subclass these and
must pass `AdapterContract` validation on landed bytes before any
benchmark use. Torch is imported lazily so CPU-only linting works.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class BandSpec:
    """Identity of one input band (SPARTINAFM_DESIGN: identity-tagged)."""
    name: str            # e.g. "B5" / "NIR"
    wavelength_um: float | None
    resolution_m: int
    sensor: str          # landsat8 / sentinel2 / sentinel1 / ...
    normalization: str | None = None   # dataset-specific stats ref


@dataclass
class ObservationBatch:
    """A batch of one observation: raster + identity metadata."""
    raster: object                     # np.ndarray (C,H,W) float32, NaN allowed
    sensor: str
    acquisition_date: str | None       # ISO date
    bands: tuple[BandSpec, ...]
    valid_mask: object | None = None   # (H,W) bool, True = QA-valid
    quality: dict = field(default_factory=dict)


@dataclass
class AdapterReport:
    """Result of contract validation on landed bytes (must be recorded)."""
    adapter_name: str
    forward_ok: bool
    output_shape: tuple | None
    finite_fraction: float | None
    errors: list[str] = field(default_factory=list)


class AdapterContract(abc.ABC):
    """Validation contract every concrete adapter must pass."""

    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    def expected_bands(self, sensor: str) -> tuple[BandSpec, ...]:
        """Band identity mapping for a sensor. Must never claim channels
        that the sensor does not physically carry."""

    @abc.abstractmethod
    def preprocess(self, batch: ObservationBatch) -> object:
        """Adapt a landed batch (native grid, NaN-aware) into model input."""

    @abc.abstractmethod
    def forward(self, model_input: object) -> object:
        """Run the model; return features or logits. No test-set access."""

    def validate_on_batch(self, batch: ObservationBatch) -> AdapterReport:
        """End-to-end validation on ONE landed batch (no training)."""
        errors = []
        try:
            x = self.preprocess(batch)
            out = self.forward(x)
            shape = tuple(getattr(out, "shape", ()))
            import numpy as np
            arr = out.detach().cpu().numpy() if hasattr(out, "detach") else np.asarray(out)
            finite = float(np.isfinite(arr).mean())
            if finite < 0.999:
                errors.append(f"non-finite fraction {1 - finite:.4f} > 0.001")
            report = AdapterReport(self.name(), True, shape, finite, errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"exception: {exc}")
            report = AdapterReport(self.name(), False, None, None, errors)
        return report


class FrozenEncoderAdapter(AdapterContract):
    """Frozen encoder + new head (regime 1/2 of FOUNDATION_MODEL_COMPARISON).

    Concrete classes must freeze weights and expose the feature map; no
    parameter updates are allowed in this regime.
    """

    @abc.abstractmethod
    def freeze_encoder(self) -> None: ...


class FineTuneAdapter(AdapterContract):
    """PEFT / full fine-tune regime (regime 3/4). Must report which
    parameters are trainable so budgets are comparable across models."""

    @abc.abstractmethod
    def trainable_parameter_report(self) -> dict: ...


class HeadSpec:
    """Segmentation head interface: 1-channel Spartina logits at the
    observation's native grid. Native-grid honesty: the head must output
    at the input grid, never claim a resolution the input lacks."""

    def __init__(self, in_features: int, native_resolution_m: int):
        self.in_features = in_features
        self.native_resolution_m = native_resolution_m

    def check_output_grid(self, out_hw, in_hw) -> bool:
        return tuple(out_hw) == tuple(in_hw)
