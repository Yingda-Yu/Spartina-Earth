"""0.5 BCEWithLogits + 0.5 Soft-Dice with explicit validity masks."""

from __future__ import annotations

import torch
from torch.nn import functional as F

_EPS = 1e-7


def bce_pos_weight(
    y: torch.Tensor, valid: torch.Tensor, cap: float = 20.0,
) -> torch.Tensor:
    """neg/pos ratio over valid TRAIN pixels, capped at ``cap``."""
    vb = valid.bool()
    pos = int(((y > 0.5) & vb).sum().item())
    neg = int(((y <= 0.5) & vb).sum().item())
    if pos == 0:
        return torch.tensor(float(cap), device=y.device)
    return torch.tensor(min(float(cap), neg / pos), device=y.device)


def segmentation_loss(
    logits: torch.Tensor, y: torch.Tensor, valid: torch.Tensor,
    pos_weight: torch.Tensor, bce_w: float = 0.5, dice_w: float = 0.5,
) -> tuple[torch.Tensor, float, float]:
    v = valid.bool().float()
    denom = v.sum().clamp_min(1.0)
    bce = F.binary_cross_entropy_with_logits(
        logits, y, pos_weight=pos_weight, reduction="none")
    bce_v = (bce * v).sum() / denom
    prob = torch.sigmoid(logits)
    inter = (prob * y * v).sum()
    dice = 1.0 - ((2.0 * inter + _EPS)
                  / ((prob * v).sum() + (y * v).sum() + _EPS))
    total = bce_w * bce_v + dice_w * dice
    return total, float(bce_v.detach().cpu()), float(dice.detach().cpu())
