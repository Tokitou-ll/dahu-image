"""启动图形界面。新功能在这里注册。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from features.image_to_pdf.feature import ImageToPdfFeature
from shared.presentation.shell.main_window import MainWindow
from shared.presentation.styles import STYLES


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("大虎图像")
    app.setOrganizationName("dahu")
    apply_theme(app)
    window = MainWindow(features=[ImageToPdfFeature()])
    window.show()
    sys.exit(app.exec())


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["PingFang SC", "Hiragino Sans GB", "Heiti SC", "Noto Sans CJK SC"])
    font.setPointSize(13)
    app.setFont(font)
    app.setStyleSheet(STYLES)
    app.setWindowIcon(_app_icon())


def _app_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1e2430"))
    painter.drawRoundedRect(4, 4, 120, 120, 28, 28)
    painter.setBrush(QColor("#d3542f"))
    painter.drawRoundedRect(30, 26, 68, 84, 8, 8)
    pen = QPen(QColor("#fffcf7"), 6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(44, 50, 84, 50)
    painter.drawLine(44, 68, 84, 68)
    painter.drawLine(44, 86, 70, 86)
    painter.end()
    return QIcon(pixmap)


if __name__ == "__main__":
    main()
