"""图片队列：缩略图、拖放和排序。"""

from __future__ import annotations

import traceback
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shared.domain.imaging import load_raster
from shared.domain.text import format_bytes

PATH_ROLE = Qt.ItemDataRole.UserRole
SIZE_ROLE = Qt.ItemDataRole.UserRole + 1


def local_paths(mime) -> list[str]:
    if mime is None or not mime.hasUrls():
        return []
    paths: list[str] = []
    for url in mime.urls():
        if url.isLocalFile():
            local = url.toLocalFile()
            if local:
                paths.append(local)
    return paths


def short_name(name: str, limit: int = 16) -> str:
    if len(name) <= limit:
        return name
    suffix = Path(name).suffix
    stem = Path(name).stem
    keep = max(1, limit - len(suffix) - 1)
    return stem[:keep] + "…" + suffix


def load_thumbnail(path: str, size: int = 256) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    if reader.canRead():
        source = reader.size()
        if source.isValid() and source.width() > 0 and source.height() > 0:
            scaled = QSize(source)
            scaled.scale(size, size, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(scaled)
            image = reader.read()
            if not image.isNull():
                return image
    raster = load_raster(path, grayscale=False)
    raster.thumbnail((size, size), Image.Resampling.LANCZOS)
    return _pil_to_qimage(raster)


def _pil_to_qimage(image: Image.Image) -> QImage:
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    wrapped = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return wrapped.copy()


class _ThumbTask(QRunnable):
    def __init__(self, path: str, ready: Signal) -> None:
        super().__init__()
        self.path = path
        self._ready = ready

    def run(self) -> None:
        try:
            image = load_thumbnail(self.path)
        except Exception:
            traceback.print_exc()
            image = QImage()
        self._ready.emit(self.path, image)


class ImageList(QListWidget):
    files_dropped = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("imageList")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(120, 120))
        self.setGridSize(QSize(148, 188))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setSpacing(6)
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def dragEnterEvent(self, event) -> None:
        if local_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if local_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = local_paths(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DropZone(QFrame):
    files_dropped = Signal(object)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("拖放图片到这里")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("也可以点击此区域选择图片\n支持 JPG、PNG、WEBP、TIFF、HEIC")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for label in (title, hint):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(title)
        layout.addWidget(hint)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if local_paths(event.mimeData()):
            event.acceptProposedAction()
            self._set_hover(True)
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_hover(False)
        paths = local_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.files_dropped.emit(paths)
        event.acceptProposedAction()

    def _set_hover(self, hover: bool) -> None:
        self.setProperty("hover", hover)
        self.style().unpolish(self)
        self.style().polish(self)


class ImageQueue(QWidget):
    files_dropped = Signal(object)
    add_clicked = Signal()
    changed = Signal()
    order_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._alive = True
        self._placeholder = self._make_placeholder()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._ready = _Ready()
        self._ready.ready.connect(self._on_thumb)

        self.drop_zone = DropZone()
        self.list = ImageList()
        self.drop_zone.files_dropped.connect(self.files_dropped.emit)
        self.drop_zone.clicked.connect(self.add_clicked.emit)
        self.list.files_dropped.connect(self.files_dropped.emit)
        self.list.model().rowsMoved.connect(lambda *_args: self.order_changed.emit())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.drop_zone, 1)
        layout.addWidget(self.list, 1)
        self._sync_empty()

    def shutdown(self) -> None:
        self._alive = False
        try:
            self._ready.ready.disconnect(self._on_thumb)
        except RuntimeError:
            pass
        self.pool.clear()
        self.pool.waitForDone(3000)

    def count(self) -> int:
        return self.list.count()

    def paths(self) -> list[str]:
        return [str(self.list.item(index).data(PATH_ROLE)) for index in range(self.list.count())]

    def total_bytes(self) -> int:
        total = 0
        for index in range(self.list.count()):
            total += int(self.list.item(index).data(SIZE_ROLE) or 0)
        return total

    def add_images(self, paths: list[str]) -> None:
        if not paths:
            return
        for path in paths:
            self._add_item(path)
        self._sync_empty()
        self.changed.emit()

    def remove_selected(self) -> int:
        items = self.list.selectedItems()
        if not items:
            return 0
        for item in items:
            self.list.takeItem(self.list.row(item))
        self._sync_empty()
        self.changed.emit()
        return len(items)

    def clear_images(self) -> None:
        if self.list.count() == 0:
            return
        self.list.clear()
        self._sync_empty()
        self.changed.emit()

    def move_current(self, delta: int) -> bool:
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.list.count():
            return False
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentItem(item)
        item.setSelected(True)
        self.order_changed.emit()
        return True

    def set_interaction_enabled(self, enabled: bool) -> None:
        self.list.setEnabled(enabled)
        self.drop_zone.setEnabled(enabled)

    def _add_item(self, path: str) -> None:
        file_path = Path(path)
        size = file_path.stat().st_size
        item = QListWidgetItem(self._placeholder, f"{short_name(file_path.name)}\n{format_bytes(size)}")
        item.setData(PATH_ROLE, path)
        item.setData(SIZE_ROLE, size)
        item.setToolTip(f"{path}\n{format_bytes(size)}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.list.addItem(item)
        task = _ThumbTask(path, self._ready.ready)
        self.pool.start(task)

    def _on_thumb(self, path: str, image: QImage) -> None:
        if not self._alive or image.isNull():
            return
        icon = QIcon(QPixmap.fromImage(image))
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(PATH_ROLE) == path:
                item.setIcon(icon)

    def _sync_empty(self) -> None:
        empty = self.list.count() == 0
        self.drop_zone.setVisible(empty)
        self.list.setVisible(not empty)

    @staticmethod
    def _make_placeholder() -> QIcon:
        pixmap = QPixmap(120, 120)
        pixmap.fill(QColor("#efe8dc"))
        return QIcon(pixmap)


class _Ready(QObject):
    ready = Signal(str, QImage)
