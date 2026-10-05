"""图片转 PDF 功能的注册入口。"""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from features.image_to_pdf.page import PdfPage


class ImageToPdfFeature:
    id = "image_to_pdf"
    title = "图片转 PDF"

    def create_page(self, settings: QSettings) -> PdfPage:
        return PdfPage(settings)

    def shutdown_page(self, page: QWidget) -> None:
        if isinstance(page, PdfPage):
            page.shutdown()
