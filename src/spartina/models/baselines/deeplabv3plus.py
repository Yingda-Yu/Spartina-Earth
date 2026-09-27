"""Standard DeepLabV3+ (smp, ResNet-18 ImageNet encoder)."""

from __future__ import annotations

from typing import Any

import segmentation_models_pytorch as smp
from torch import nn

from spartina.models.baselines.inflation import replace_conv_weights
from spartina.models.baselines.unet import ENCODER, UPSTREAM, weights_file_sha256


def build_deeplabv3plus(
    in_channels: int, pretrained: bool = True,
) -> tuple[nn.Module, dict[str, Any]]:
    if not pretrained:
        model = smp.DeepLabV3Plus(
            encoder_name=ENCODER, encoder_weights=None,
            in_channels=in_channels, classes=1)
        return model, {"pretrained": False}
    pre = smp.DeepLabV3Plus(
        encoder_name=ENCODER, encoder_weights="imagenet",
        in_channels=3, classes=1)
    rgb = pre.encoder.conv1.weight.detach().clone()
    if in_channels == 3:
        model = pre
    else:
        model = smp.DeepLabV3Plus(
            encoder_name=ENCODER, encoder_weights=None,
            in_channels=in_channels, classes=1)
        replace_conv_weights(model.encoder.conv1, rgb)
    meta = {"pretrained": True, **UPSTREAM,
            "weights_sha256": weights_file_sha256(),
            "channel_inflation": "mean RGB kernel -> replicate -> *3/C"}
    return model, meta
