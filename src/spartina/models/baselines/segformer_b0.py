"""SegFormer-B0 semantic segmenter (NVIDIA pretrained checkpoint).

The standard ``nvidia/segformer-b0-finetuned-ade-512-512`` encoder is
used; only the 150-class classification head is replaced by a 1-class
head. Logits (H/4 x W/4) are bilinearly upsampled to the input size.
First-layer channel inflation uses the same mean-RGB-kernel rule.
"""

from __future__ import annotations

from typing import Any

import torch
from torch import nn
from torch.nn import functional as F
from transformers import SegformerForSemanticSegmentation

from spartina.models.baselines.inflation import replace_conv_weights

HF_NAME = "nvidia/segformer-b0-finetuned-ade-512-512"
UPSTREAM = {
    "name": HF_NAME,
    "version": "transformers 4.46.3; NVIDIA SegFormer-B0 (ADE20K head, "
               "ImageNet-pretrained encoder family)",
    "license": "Apache-2.0",
    "url": f"https://huggingface.co/{HF_NAME}",
}


class SegFormerB0(nn.Module):
    def __init__(self, hf_model: SegformerForSemanticSegmentation) -> None:
        super().__init__()
        self.hf = hf_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.hf(pixel_values=x).logits
        out: torch.Tensor = F.interpolate(
            logits, size=x.shape[-2:], mode="bilinear",
            align_corners=False)
        return out


def build_segformer_b0(
    in_channels: int, pretrained: bool = True,
) -> tuple[nn.Module, dict[str, Any]]:
    if not pretrained:
        raise RuntimeError(
            "SegFormer-B0 pretrained weights are mandatory in M1.5; "
            "refusing a silent scratch build")
    hf = SegformerForSemanticSegmentation.from_pretrained(
        HF_NAME, num_labels=1, ignore_mismatched_sizes=True)
    revision = getattr(hf.config, "_commit_hash", None)
    proj = hf.segformer.encoder.patch_embeddings[0].proj
    if in_channels != 3:
        rgb = proj.weight.detach().clone()
        new_proj = nn.Conv2d(
            in_channels, proj.out_channels, kernel_size=proj.kernel_size,
            stride=proj.stride, padding=proj.padding, bias=proj.bias is not None)
        replace_conv_weights(new_proj, rgb)
        hf.segformer.encoder.patch_embeddings[0].proj = new_proj
    meta = {"pretrained": True, **UPSTREAM,
            "revision": str(revision) if revision else "UNKNOWN",
            "channel_inflation": "mean RGB kernel -> replicate -> *3/C"}
    return SegFormerB0(hf), meta
