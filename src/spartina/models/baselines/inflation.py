"""Deterministic first-layer channel inflation (Issue #5 section 6).

Single rule used for every input variant and every architecture:

1. average the pretrained RGB first-layer kernels over input channels;
2. replicate that mean kernel to all ``C`` input channels;
3. multiply by ``3 / C`` to preserve approximate fan-in magnitude.
"""

from __future__ import annotations

import torch
from torch import nn


def inflate_kernel(rgb_weight: torch.Tensor, in_channels: int) -> torch.Tensor:
    if rgb_weight.ndim != 4 or rgb_weight.shape[1] != 3:
        raise ValueError("expected pretrained RGB kernel (O,3,kH,kW)")
    mean = rgb_weight.detach().mean(dim=1, keepdim=True)
    return mean.repeat(1, in_channels, 1, 1) * (3.0 / float(in_channels))


def replace_conv_weights(conv: nn.Conv2d, rgb_weight: torch.Tensor) -> None:
    c = conv.in_channels
    with torch.no_grad():
        conv.weight.copy_(inflate_kernel(rgb_weight, c))
        if conv.bias is not None:
            conv.bias.zero_()
