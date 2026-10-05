"""导出参数。页面尺寸、分辨率上限和 JPEG 质量都从这里读。"""

from __future__ import annotations

from dataclasses import dataclass

from shared.domain.imaging import JPEG_QUALITY_MAX, JPEG_QUALITY_MIN


PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a4": (210.0, 297.0),
    "a4_land": (297.0, 210.0),
    "letter": (215.9, 279.4),
    "letter_land": (279.4, 215.9),
}

PAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("a4", "A4 纵向"),
    ("a4_land", "A4 横向"),
    ("letter", "Letter 纵向"),
    ("letter_land", "Letter 横向"),
    ("original", "原始比例"),
)

SIZING_CHOICES: tuple[tuple[str, str], ...] = (
    ("manual", "手动调节"),
    ("target", "按目标体积"),
)

MIN_JPEG_QUALITY = JPEG_QUALITY_MIN
MAX_JPEG_QUALITY = JPEG_QUALITY_MAX
MIN_DPI = 72
MAX_DPI = 400
MIN_EDGE = 640
MAX_EDGE = 6000
MIN_MARGIN_MM = 0.0
MAX_MARGIN_MM = 30.0
MIN_TARGET_MB = 0.2
MAX_TARGET_MB = 200.0
# 自动匹配时，分辨率最低降到用户上限的这个比例，避免文字小到无法阅读。
MIN_TARGET_SCALE = 0.4
ORIGINAL_PAGE_DPI = 96


@dataclass(frozen=True)
class QualityPreset:
    key: str
    label: str
    detail: str
    dpi: int
    max_long_edge: int
    jpeg_quality: int


PRESETS: dict[str, QualityPreset] = {
    "small": QualityPreset("small", "小文件", "适合微信、邮件", 96, 1280, 60),
    "standard": QualityPreset("standard", "标准", "日常归档", 150, 1920, 75),
    "high": QualityPreset("high", "高清", "屏幕放大仍清楚", 200, 2560, 85),
    "print": QualityPreset("print", "印刷", "接近打印所需", 300, 3500, 92),
}

PRESET_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (preset.key, f"{preset.label}（{preset.detail}）") for preset in PRESETS.values()
) + (("custom", "自定义"),)


@dataclass(frozen=True)
class ExportSettings:
    page: str = "a4"
    dpi: int = 150
    max_long_edge: int = 1920
    jpeg_quality: int = 75
    margin_mm: float = 8.0
    grayscale: bool = False
    auto_orient: bool = True
    sizing: str = "manual"
    target_mb: float = 5.0

    def clamped(self) -> ExportSettings:
        page = self.page if self.page in dict(PAGE_CHOICES) else "a4"
        sizing = self.sizing if self.sizing in dict(SIZING_CHOICES) else "manual"
        return ExportSettings(
            page=page,
            dpi=_clamp_int(self.dpi, MIN_DPI, MAX_DPI),
            max_long_edge=_clamp_int(self.max_long_edge, MIN_EDGE, MAX_EDGE),
            jpeg_quality=_clamp_int(self.jpeg_quality, MIN_JPEG_QUALITY, MAX_JPEG_QUALITY),
            margin_mm=_clamp_float(self.margin_mm, MIN_MARGIN_MM, MAX_MARGIN_MM),
            grayscale=bool(self.grayscale),
            auto_orient=bool(self.auto_orient),
            sizing=sizing,
            target_mb=_clamp_float(self.target_mb, MIN_TARGET_MB, MAX_TARGET_MB),
        )

    @property
    def target_bytes(self) -> int:
        return int(self.target_mb * 1024 * 1024)


class SettingsError(ValueError):
    """参数不合法，可以直接显示给用户。"""


def validate_settings(settings: ExportSettings) -> None:
    settings = settings.clamped()
    if settings.page not in PAGE_SIZES_MM and settings.page != "original":
        raise SettingsError("不支持的页面尺寸")
    if settings.sizing not in dict(SIZING_CHOICES):
        raise SettingsError("不支持的压缩方式")
    if settings.page != "original":
        width, height = PAGE_SIZES_MM[settings.page]
        content_w = width - 2 * settings.margin_mm
        content_h = height - 2 * settings.margin_mm
        if content_w < 20 or content_h < 20:
            raise SettingsError("页边距太大，可打印区域不足 20 毫米")


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))
