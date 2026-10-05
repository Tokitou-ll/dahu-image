"""把多张图片压成一个 PDF。

体积几乎等于各页 JPEG 的大小。处理顺序是：

1. 按拍摄方向转正，透明背景铺白，动图只留第一帧。
2. 先降分辨率。固定纸张的像素上限是「去掉边距后的尺寸 × DPI」；
   原始比例只限制最长边。边长减半，像素大约剩四分之一，这是主要杠杆。
   小图不放大。
3. 再按 JPEG 质量重编码。质量越高，色彩抽样越少：90 及以上用 4:4:4，
   75 到 89 用 4:2:2，更低用 4:2:0。
4. JPEG 原样嵌入 PDF，不再压缩第二次。

按目标体积时，先在当前分辨率下二分查找能放进目标的最高质量。
最低质量仍超标，就按面积比例（边长按平方根）继续缩小，直到放进目标，
或到达可读下限（质量 35、分辨率约为上限的 40%）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import img2pdf
from PIL import Image

from features.image_to_pdf.prepare import fit_image, output_dpi, scale_master
from features.image_to_pdf.settings import (
    MIN_JPEG_QUALITY,
    MIN_TARGET_SCALE,
    PAGE_SIZES_MM,
    ExportSettings,
    SettingsError,
    validate_settings,
)
from shared.domain.errors import Cancelled
from shared.domain.imaging import encode_jpeg, load_raster

ProgressFn = Callable[[int, int, str], None]
CancelFn = Callable[[], bool]


class ExportCancelled(Cancelled):
    """用户取消，或一次新的任务替换了当前任务。"""


@dataclass
class Plan:
    jpeg_pages: list[bytes]
    source_bytes: int
    quality: int
    scale: float
    effective_dpi: int
    max_edge: int
    hit_target: bool
    note: str

    @property
    def jpeg_bytes(self) -> int:
        return sum(len(page) for page in self.jpeg_pages)

    @property
    def page_count(self) -> int:
        return len(self.jpeg_pages)


@dataclass
class ExportOutcome:
    output_path: str
    output_bytes: int
    page_count: int
    note: str
    source_bytes: int
    hit_target: bool
    quality: int
    scale: float


def approximate_pdf_size(jpeg_bytes: int, pages: int) -> int:
    return jpeg_bytes + 12_288 + 2_048 * max(pages, 1)


def plan_pages(
    paths: list[str],
    settings: ExportSettings,
    on_progress: ProgressFn | None = None,
    is_cancelled: CancelFn | None = None,
) -> Plan:
    settings = settings.clamped()
    validate_settings(settings)
    if not paths:
        raise SettingsError("请先添加图片")
    cancelled = is_cancelled or (lambda: False)

    def report(done: int, total: int, message: str) -> None:
        if cancelled():
            raise ExportCancelled()
        if on_progress is not None:
            on_progress(done, total, message)

    source_bytes = 0
    for path in paths:
        file_path = Path(path)
        if not file_path.is_file():
            raise SettingsError(f"找不到文件「{file_path.name}」")
        source_bytes += file_path.stat().st_size

    total = len(paths)
    if settings.sizing == "manual":
        pages: list[bytes] = []
        max_edge = 1
        for index, path in enumerate(paths, start=1):
            report(index - 1, total, f"正在压缩 {Path(path).name}")
            raster = load_raster(path, grayscale=settings.grayscale)
            fitted = fit_image(raster, settings, 1.0)
            max_edge = max(max_edge, fitted.width, fitted.height)
            pages.append(encode_jpeg(fitted, settings.jpeg_quality, output_dpi(settings, 1.0)))
        report(total, total, "压缩完成")
        return Plan(
            jpeg_pages=pages,
            source_bytes=source_bytes,
            quality=settings.jpeg_quality,
            scale=1.0,
            effective_dpi=output_dpi(settings, 1.0),
            max_edge=max_edge,
            hit_target=True,
            note=_describe(
                settings,
                settings.jpeg_quality,
                1.0,
                True,
                output_dpi(settings, 1.0),
                max_edge,
            ),
        )

    masters: list[Image.Image] = []
    for index, path in enumerate(paths, start=1):
        report(index - 1, total, f"正在读取 {Path(path).name}")
        raster = load_raster(path, grayscale=settings.grayscale)
        masters.append(fit_image(raster, settings, 1.0))
    quality, scale, pages, hit, max_edge = _match_target(masters, settings, report, cancelled)
    dpi = output_dpi(settings, scale)
    report(total, total, "压缩完成")
    return Plan(
        jpeg_pages=pages,
        source_bytes=source_bytes,
        quality=quality,
        scale=scale,
        effective_dpi=dpi,
        max_edge=max_edge,
        hit_target=hit,
        note=_describe(settings, quality, scale, hit, dpi, max_edge),
    )


def write_pdf(jpeg_pages: list[bytes], settings: ExportSettings, output_path: Path) -> int:
    if not jpeg_pages:
        raise SettingsError("没有可写入的页面")
    settings = settings.clamped()
    kwargs: dict = {"creator": "dahu-image", "producer": "dahu-image"}
    layout = _layout_for(settings)
    if layout is not None:
        kwargs["layout_fun"] = layout
    try:
        pdf = img2pdf.convert(jpeg_pages, **kwargs)
    except Exception as exc:
        raise SettingsError(f"生成 PDF 失败：{exc}") from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(output_path.name + ".part")
    try:
        partial.write_bytes(pdf)
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return output_path.stat().st_size


def _layout_for(settings: ExportSettings):
    if settings.page == "original":
        return None
    width_mm, height_mm = PAGE_SIZES_MM[settings.page]
    page = (img2pdf.mm_to_pt(width_mm), img2pdf.mm_to_pt(height_mm))
    margin = img2pdf.mm_to_pt(settings.margin_mm)
    # img2pdf 的边距是 (垂直, 水平)，单位是点。
    return img2pdf.get_layout_fun(
        pagesize=page,
        border=(margin, margin),
        fit=img2pdf.FitMode.into,
        auto_orient=settings.auto_orient,
    )


def _match_target(
    masters: list[Image.Image],
    settings: ExportSettings,
    report: ProgressFn,
    cancelled: CancelFn,
) -> tuple[int, float, list[bytes], bool, int]:
    """返回 (质量, 缩放, JPEG 页, 是否放进目标, 实际最长边)。"""
    budget = _jpeg_budget(settings.target_bytes, len(masters))
    ceiling = settings.jpeg_quality
    scale = 1.0
    smallest: tuple[int, float, list[bytes], int] | None = None

    for attempt in range(6):
        if cancelled():
            raise ExportCancelled()
        working, owned = _scaled(masters, scale)
        try:
            edge = _max_edge(working)
            found = _highest_quality(working, ceiling, budget, settings, scale, report, cancelled)
            if found is not None:
                quality, pages = found
                return quality, scale, pages, True, edge
            floor_pages = _encode_all(working, MIN_JPEG_QUALITY, output_dpi(settings, scale), cancelled)
            floor_size = sum(len(page) for page in floor_pages)
            smallest = (MIN_JPEG_QUALITY, scale, floor_pages, edge)
            if floor_size <= budget:
                return MIN_JPEG_QUALITY, scale, floor_pages, True, edge
            if scale <= MIN_TARGET_SCALE + 1e-6:
                break
            # JPEG 体积大致随像素面积变化，所以边长按平方根缩小，并留一点余量。
            ratio = budget / max(floor_size, 1)
            proposed = scale * math.sqrt(ratio) * 0.90
            next_scale = max(MIN_TARGET_SCALE, min(proposed, scale * 0.85))
            if next_scale >= scale - 0.01:
                break
            scale = next_scale
            report(attempt, 6, f"质量 {MIN_JPEG_QUALITY} 仍然太大，继续降低分辨率")
        finally:
            for image in owned:
                image.close()

    if smallest is None:
        raise SettingsError("没有生成任何页面")
    quality, scale, pages, edge = smallest
    return quality, scale, pages, False, edge


def _highest_quality(
    images: list[Image.Image],
    ceiling: int,
    budget: int,
    settings: ExportSettings,
    scale: float,
    report: ProgressFn,
    cancelled: CancelFn,
) -> tuple[int, list[bytes]] | None:
    low = MIN_JPEG_QUALITY
    high = max(MIN_JPEG_QUALITY, ceiling)
    found: tuple[int, list[bytes]] | None = None
    dpi = output_dpi(settings, scale)
    while low <= high:
        if cancelled():
            raise ExportCancelled()
        quality = (low + high) // 2
        percent = int(round(scale * 100))
        report(0, 0, f"正在试 JPEG 质量 {quality}（分辨率 {percent}%）")
        pages = _encode_all(images, quality, dpi, cancelled)
        size = sum(len(page) for page in pages)
        if size <= budget:
            found = (quality, pages)
            low = quality + 1
        else:
            high = quality - 1
    return found


def _encode_all(
    images: list[Image.Image],
    quality: int,
    dpi: int,
    cancelled: CancelFn,
) -> list[bytes]:
    pages: list[bytes] = []
    for image in images:
        if cancelled():
            raise ExportCancelled()
        pages.append(encode_jpeg(image, quality, dpi))
    return pages


def _scaled(masters: list[Image.Image], scale: float) -> tuple[list[Image.Image], list[Image.Image]]:
    if scale >= 0.999:
        return list(masters), []
    working: list[Image.Image] = []
    owned: list[Image.Image] = []
    for image in masters:
        scaled = scale_master(image, scale)
        working.append(scaled)
        if scaled is not image:
            owned.append(scaled)
    return working, owned


def _max_edge(images: list[Image.Image]) -> int:
    if not images:
        return 1
    return max(max(image.width, image.height) for image in images)


def _jpeg_budget(target_bytes: int, pages: int) -> int:
    # 预留 PDF 结构开销，让最终文件落在目标以内，而不是刚好卡在 JPEG 字节数上。
    overhead = 24_576 + 4_096 * pages
    return max(8_192, target_bytes - overhead)


def _describe(
    settings: ExportSettings,
    quality: int,
    _scale: float,
    hit_target: bool,
    dpi: int,
    max_edge: int,
) -> str:
    if settings.page == "original":
        geometry = f"最长边 {max_edge} 像素"
    else:
        geometry = f"{dpi} DPI"
    color = "已转为黑白。" if settings.grayscale else ""
    if settings.sizing == "manual":
        return f"{geometry}，JPEG 质量 {quality}。{color}"
    target = f"{settings.target_mb:.1f} MB"
    if hit_target:
        return f"为放进 {target}，使用 {geometry}，JPEG 质量 {quality}。{color}"
    return f"已降到 {geometry}、JPEG 质量 {quality}，仍大于目标 {target}。{color}"


ALGORITHM_HELP = """PDF 有多大，主要看嵌进去的图片有多大。程序按这个顺序处理每一张图：

1. 按拍摄方向转正。透明背景铺成白色。动图只用第一帧。
2. 先算一个像素上限。
   · 选了 A4 或 Letter：上限 = 去掉页边距后的纸张尺寸 × 分辨率（DPI）。
   · 选了原始比例：上限是最长边的像素。
   图片会按比例缩小到这个上限里。小图不会被放大。
3. 用 Lanczos 重采样缩小。边长变成一半时，像素大约剩四分之一，文件通常会小到原来的三分之一到四分之一。这是控制体积的主要办法。
4. 再压成 JPEG。质量越高越清晰，文件越大。
   · 90 及以上：保留完整色彩，适合印刷。
   · 75 到 89：略微合并色彩，体积更小。
   · 75 以下：使用更强的色彩抽样，适合发送。
5. 这些 JPEG 直接放进 PDF，不再压缩第二次，避免越压越糊。

选「按目标体积」时，会先在分辨率上限内，从高到低找能放进目标的最高 JPEG 质量。最低质量仍然放不下，就按面积比例继续缩小分辨率，直到放进目标，或者到达可读下限（质量 35、分辨率约为上限的 40%）。

勾选黑白会去掉色彩，一般还能再小一截。小图放在 A4 上时，阅读器会把它拉到页面里，文件不会因此变大，但模糊的图也不会变清楚。"""
