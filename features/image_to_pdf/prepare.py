"""按 PDF 页面设置计算像素上限，再调用共享的缩小函数。"""

from __future__ import annotations

import math

from PIL import Image

from features.image_to_pdf.settings import (
    ORIGINAL_PAGE_DPI,
    PAGE_SIZES_MM,
    ExportSettings,
)
from shared.domain.imaging import resize_within, scale_image


def pixel_limit(
    settings: ExportSettings,
    scale: float,
    src_w: int,
    src_h: int,
) -> tuple[int, int]:
    """返回这一张图允许的最大宽高。

    固定纸张用「可打印区域 × DPI」。勾选自动旋转时，横图按横页计算，
    这样横图不会被竖页的短边提前压小。原始比例只限制最长边。
    """
    scale = max(0.05, float(scale))
    if settings.page == "original":
        edge = max(1, int(round(settings.max_long_edge * scale)))
        return edge, edge

    width_mm, height_mm = PAGE_SIZES_MM[settings.page]
    if settings.auto_orient and src_w != src_h:
        image_landscape = src_w > src_h
        page_landscape = width_mm > height_mm
        if image_landscape != page_landscape:
            width_mm, height_mm = height_mm, width_mm
    content_w = max(1.0, width_mm - 2 * settings.margin_mm)
    content_h = max(1.0, height_mm - 2 * settings.margin_mm)
    dpi = settings.dpi * scale
    max_w = max(1, int(math.floor(content_w / 25.4 * dpi)))
    max_h = max(1, int(math.floor(content_h / 25.4 * dpi)))
    return max_w, max_h


def output_dpi(settings: ExportSettings, scale: float) -> int:
    if settings.page == "original":
        return ORIGINAL_PAGE_DPI
    return max(36, int(round(settings.dpi * scale)))


def fit_image(image: Image.Image, settings: ExportSettings, scale: float) -> Image.Image:
    """缩小到像素上限以内。不放大小图，避免文件变大却没有更多细节。"""
    max_w, max_h = pixel_limit(settings, scale, image.width, image.height)
    return resize_within(image, max_w, max_h)


def scale_master(image: Image.Image, scale: float) -> Image.Image:
    """在已经缩小过的图上再按比例缩小，供目标体积的后续尝试使用。"""
    return scale_image(image, scale)
