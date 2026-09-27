"""Standard baseline segmentation models for Pilot-0 (M1.5).

No custom Spartina architecture lives here: U-Net and DeepLabV3+ use
standard segmentation-models-pytorch builds with ImageNet ResNet-18
encoders; SegFormer-B0 uses the standard NVIDIA pretrained checkpoint.
"""

from __future__ import annotations

from spartina.models.baselines.deeplabv3plus import build_deeplabv3plus
from spartina.models.baselines.segformer_b0 import build_segformer_b0
from spartina.models.baselines.unet import build_unet

MODEL_BUILDERS = {
    "unet": build_unet,
    "deeplabv3plus": build_deeplabv3plus,
    "segformer_b0": build_segformer_b0,
}

__all__ = ["MODEL_BUILDERS", "build_unet", "build_deeplabv3plus",
           "build_segformer_b0"]
