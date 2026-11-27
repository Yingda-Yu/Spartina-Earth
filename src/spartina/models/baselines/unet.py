"""Standard U-Net (smp, ResNet-18 ImageNet encoder)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import segmentation_models_pytorch as smp
from torch import nn

from spartina.models.baselines.inflation import replace_conv_weights

ENCODER = "resnet18"
WEIGHTS_FILE = "resnet18-5c106cde.pth"
UPSTREAM = {
    "name": "torchvision resnet18 ImageNet classification weights",
    "version": "torchvision 0.20.1 / ResNet18_Weights.IMAGENET1K_V1",
    "license": "BSD-3-Clause (weights); ImageNet terms for data",
    "url": f"https://download.pytorch.org/models/{WEIGHTS_FILE}",
}


def weights_file_sha256() -> str | None:
    p = Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / WEIGHTS_FILE
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_unet(
    in_channels: int, pretrained: bool = True,
) -> tuple[nn.Module, dict[str, Any]]:
    if not pretrained:
        model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                         in_channels=in_channels, classes=1)
        return model, {"pretrained": False}
    pre = smp.Unet(encoder_name=ENCODER, encoder_weights="imagenet",
                   in_channels=3, classes=1)
    rgb = pre.encoder.conv1.weight.detach().clone()
    if in_channels == 3:
        model = pre
    else:
        model = smp.Unet(encoder_name=ENCODER, encoder_weights=None,
                         in_channels=in_channels, classes=1)
        replace_conv_weights(model.encoder.conv1, rgb)
    meta = {"pretrained": True, **UPSTREAM,
            "weights_sha256": weights_file_sha256(),
            "channel_inflation": "mean RGB kernel -> replicate -> *3/C"}
    return model, meta
