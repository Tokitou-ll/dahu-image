"""功能注册约定。窗口只依赖这个约定。"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget


class Feature(Protocol):
    """一项可以出现在侧栏里的功能。

    create_page 返回该功能的整页。shutdown_page 在窗口关闭时调用。
    """

    id: str
    title: str

    def create_page(self, settings: QSettings) -> QWidget: ...

    def shutdown_page(self, page: QWidget) -> None: ...
