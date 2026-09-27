"""Cosine decay with a short linear warmup (identical per architecture)."""

from __future__ import annotations

import math

import numpy as np


def lr_at_epoch(
    base_lr: float, epoch: int, max_epochs: int, warmup_epochs: int,
) -> float:
    if epoch < warmup_epochs:
        return base_lr * (epoch + 1) / max(1, warmup_epochs)
    progress = (epoch - warmup_epochs) / max(1, max_epochs - warmup_epochs)
    progress = min(1.0, max(0.0, progress))
    return base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))


def seed_everything(seed: int) -> None:
    import os
    import random

    import torch
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
