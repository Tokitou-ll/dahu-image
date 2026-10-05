"""主窗口。侧栏和页面都来自传入的功能列表。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from version import __version__
from shared.presentation.shell.feature import Feature


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: QSettings | None = None,
        features: Sequence[Feature] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings or QSettings("dahu", "dahu-image")
        self._features = list(features or [])
        self._order: list[str] = []
        self._feature_by_id: dict[str, Feature] = {}
        self._page_by_id: dict[str, QWidget] = {}
        self._nav_buttons: list[QPushButton] = []

        self.setWindowTitle("大虎图像")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)

        root = QWidget()
        root.setObjectName("root")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("stack")
        self._stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._mount_features()
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._stack, 1)

        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def page_for(self, feature_id: str) -> QWidget:
        return self._page_by_id[feature_id]

    def current_page(self) -> QWidget | None:
        return self._stack.currentWidget()

    def show_feature(self, feature_id: str) -> None:
        index = self._order.index(feature_id)
        self._stack.setCurrentIndex(index)
        self._select_nav(index)

    def closeEvent(self, event) -> None:
        for feature_id in self._order:
            self._feature_by_id[feature_id].shutdown_page(self._page_by_id[feature_id])
        self._settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def _mount_features(self) -> None:
        seen: set[str] = set()
        for feature in self._features:
            if feature.id in seen:
                raise ValueError(f"功能标识重复：{feature.id}")
            seen.add(feature.id)
            page = feature.create_page(self._settings)
            self._order.append(feature.id)
            self._feature_by_id[feature.id] = feature
            self._page_by_id[feature.id] = page
            self._stack.addWidget(page)

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(208)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(20, 28, 20, 20)
        layout.setSpacing(6)
        title = QLabel("大虎图像")
        title.setObjectName("sideTitle")
        subtitle = QLabel("图片与 PDF")
        subtitle.setObjectName("sideSubtitle")
        later = QLabel("其他工具以后加在这里")
        later.setObjectName("navSoon")
        later.setWordWrap(True)
        version = QLabel(f"版本 {__version__}")
        version.setObjectName("sideVersion")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(28)
        for index, feature in enumerate(self._features):
            button = QPushButton(feature.title)
            button.setObjectName("navCurrent" if index == 0 else "navItem")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, feature_id=feature.id: self.show_feature(feature_id)
            )
            layout.addWidget(button)
            self._nav_buttons.append(button)
        layout.addStretch(1)
        layout.addWidget(later)
        layout.addWidget(version)
        return side

    def _select_nav(self, index: int) -> None:
        for button_index, button in enumerate(self._nav_buttons):
            button.setObjectName("navCurrent" if button_index == index else "navItem")
            button.style().unpolish(button)
            button.style().polish(button)
