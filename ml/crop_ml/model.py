from __future__ import annotations

from pathlib import Path

import numpy as np
import timm
import torch
from PIL import Image, ImageOps
from torch import nn

from .common import MODEL_NAME

IMAGE_SIZE = 224
PADDING_RGB = (124, 116, 104)
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def prepare_image(image: Image.Image) -> np.ndarray:
    """EXIF-normalized RGB, aspect-preserving letterbox, float NCHW tensor."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("Image has no pixels")
    scale = min(IMAGE_SIZE / width, IMAGE_SIZE / height)
    # Explicit half-up rounding is reproducible on Android (avoid Python banker's round).
    resized = (max(1, int(width * scale + 0.5)), max(1, int(height * scale + 0.5)))
    image = image.resize(resized, Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), PADDING_RGB)
    canvas.paste(image, ((IMAGE_SIZE - resized[0]) // 2, (IMAGE_SIZE - resized[1]) // 2))
    values = np.asarray(canvas, dtype=np.float32) / np.float32(255)
    values = (values - np.asarray(MEAN, dtype=np.float32)) / np.asarray(STD, dtype=np.float32)
    return np.ascontiguousarray(values.transpose(2, 0, 1))


class CropModel(nn.Module):
    """V4-Conv-Small with classifier logits and dynamically measured pooled embeddings."""
    def __init__(self, pretrained: bool = False, checkpoint: Path | None = None):
        super().__init__()
        self.backbone = timm.create_model(MODEL_NAME, pretrained=pretrained, num_classes=17)
        if checkpoint:
            if checkpoint.suffix == ".safetensors":
                from safetensors.torch import load_file
                state = load_file(str(checkpoint))
            else:
                state = torch.load(checkpoint, map_location="cpu", weights_only=True)
                state = state.get("state_dict", state)
            # ImageNet classifier shape differs; all remaining pretrained tensors must match.
            expected = self.backbone.state_dict()
            state = {k: v for k, v in state.items() if k in expected and v.shape == expected[k].shape}
            missing, unexpected = self.backbone.load_state_dict(state, strict=False)
            if any(not name.startswith("classifier.") for name in missing) or unexpected:
                raise ValueError(f"Checkpoint is not a complete compatible V4 backbone: {missing}, {unexpected}")

    def forward(self, image):
        spatial = self.backbone.forward_features(image)
        logits = self.backbone.forward_head(spatial)
        embeddings = spatial.mean(dim=(2, 3))
        return logits, embeddings

    def freeze_backbone(self):
        for p in self.backbone.parameters():
            p.requires_grad_(False)
        for p in self.backbone.get_classifier().parameters():
            p.requires_grad_(True)
