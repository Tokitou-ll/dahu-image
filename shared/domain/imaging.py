"""打开、校正并缩小图片，再编码成 JPEG。不依赖界面，也不知道 PDF。"""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageOps

from shared.domain.errors import ImagePrepareError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


JPEG_QUALITY_MIN = 35
JPEG_QUALITY_MAX = 95


def load_raster(path: str | Path, *, grayscale: bool) -> Image.Image:
    """打开图片，转正方向，去掉透明通道。动图只取第一帧。"""
    file_path = Path(path)
    try:
        with Image.open(file_path) as source:
            source.seek(0)
            source.load()
            oriented = ImageOps.exif_transpose(source) or source
            flat = flatten_image(oriented, grayscale=grayscale)
            return flat.copy()
    except Image.DecompressionBombError as exc:
        raise ImagePrepareError(file_path, "图片像素过多，请先缩小后再导入") from exc
    except ImagePrepareError:
        raise
    except Exception as exc:
        raise ImagePrepareError(file_path, str(exc)) from exc


def flatten_image(image: Image.Image, *, grayscale: bool) -> Image.Image:
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    if image.mode in ("RGBA", "LA"):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    if grayscale:
        return image.convert("L")
    return image


def resize_within(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """缩小到给定宽高以内。不放大。"""
    fitted = _fit_size(image.width, image.height, max_w, max_h)
    if fitted == image.size:
        return image
    return image.resize(fitted, Image.Resampling.LANCZOS)


def scale_image(image: Image.Image, scale: float) -> Image.Image:
    """按比例再缩小。比例接近 1 时返回原图。"""
    if scale >= 0.999:
        return image
    width = max(1, int(math.floor(image.width * scale)))
    height = max(1, int(math.floor(image.height * scale)))
    if (width, height) == image.size:
        return image
    return image.resize((width, height), Image.Resampling.LANCZOS)


def encode_jpeg(image: Image.Image, quality: int, dpi: int) -> bytes:
    quality = max(JPEG_QUALITY_MIN, min(JPEG_QUALITY_MAX, int(quality)))
    buffer = io.BytesIO()
    options: dict = {
        "format": "JPEG",
        "quality": quality,
        "optimize": True,
        "dpi": (int(dpi), int(dpi)),
    }
    # 灰度图没有色度可抽样。彩色图在强压缩时丢掉一部分色彩分辨率，体积会小一截。
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if image.mode == "RGB":
        subsampling = _chroma_subsampling(quality)
        options["subsampling"] = subsampling
        # 这套 libjpeg 在优化哈夫曼表的同时使用 4:4:4，会写出损坏的数据流。
        if subsampling == "4:4:4":
            options["optimize"] = False
    image.save(buffer, **options)
    return buffer.getvalue()


def _chroma_subsampling(quality: int) -> str:
    if quality >= 90:
        return "4:4:4"
    if quality >= 75:
        return "4:2:2"
    return "4:2:0"


def _fit_size(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
    if src_w <= 0 or src_h <= 0:
        raise ValueError("图片尺寸无效")
    scale = min(max_w / src_w, max_h / src_h, 1.0)
    width = max(1, int(math.floor(src_w * scale + 1e-9)))
    height = max(1, int(math.floor(src_h * scale + 1e-9)))
    return min(width, max_w), min(height, max_h)
