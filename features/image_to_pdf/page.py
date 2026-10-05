"""图片转 PDF 页面。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from features.image_to_pdf.jobs import EstimateJob, ExportJob
from features.image_to_pdf.service import (
    ALGORITHM_HELP,
    ExportOutcome,
    Plan,
    approximate_pdf_size,
)
from features.image_to_pdf.settings import (
    MAX_DPI,
    MAX_EDGE,
    MAX_JPEG_QUALITY,
    MAX_MARGIN_MM,
    MAX_TARGET_MB,
    MIN_DPI,
    MIN_EDGE,
    MIN_JPEG_QUALITY,
    MIN_MARGIN_MM,
    MIN_TARGET_MB,
    PAGE_CHOICES,
    PRESETS,
    PRESET_CHOICES,
    SIZING_CHOICES,
    ExportSettings,
    SettingsError,
    validate_settings,
)
from shared.domain.files import collect_inputs, image_dialog_filter
from shared.domain.text import format_bytes
from shared.presentation.jobs import JobRunner
from shared.presentation.widgets.image_queue import ImageQueue


class PdfPage(QWidget):
    export_succeeded = Signal(object)
    export_failed = Signal(str)
    export_cancelled = Signal()

    def __init__(self, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._store = settings
        self._alive = True
        self._applying = 0
        self._exporting = False
        self._estimating = False
        self._last_dir = str(Path.home())
        self._cached_signature: tuple | None = None
        self._cached_plan: Plan | None = None
        self.show_result_dialog = True
        self._runner = JobRunner(self)
        self._estimate_timer = QTimer(self)
        self._estimate_timer.setSingleShot(True)
        self._estimate_timer.setInterval(600)
        self._estimate_timer.timeout.connect(self._start_estimate)

        self.queue = ImageQueue()
        self._build()
        self._load_settings()
        self._bind()
        self._sync_mode()
        self._update_count()
        self._sync_buttons()

    def shutdown(self) -> None:
        self._alive = False
        self._estimate_timer.stop()
        self._runner.shutdown()
        self.queue.shutdown()
        self.save_settings()

    def add_paths(self, raw_paths: list[str]) -> str:
        collected = collect_inputs(list(raw_paths))
        existing = set(self.queue.paths())
        fresh: list[str] = []
        duplicates = 0
        for path in collected.images:
            if path in existing:
                duplicates += 1
                continue
            existing.add(path)
            fresh.append(path)
        if fresh:
            self.queue.add_images(fresh)
        parts: list[str] = []
        if fresh:
            parts.append(f"已添加 {len(fresh)} 张")
        if duplicates:
            parts.append(f"{duplicates} 张已在列表中")
        if collected.skipped:
            parts.append(f"跳过 {len(collected.skipped)} 个不支持的文件")
        if collected.missing:
            parts.append(f"{len(collected.missing)} 个路径不存在")
        message = "，".join(parts) if parts else "没有找到支持的图片"
        self.status_label.setText(message)
        return message

    def export_to(self, output_path: str) -> None:
        if not self._alive:
            return
        if self.queue.count() == 0:
            self._fail_soon("请先添加图片")
            return
        settings = self.current_settings()
        try:
            validate_settings(settings)
        except SettingsError as exc:
            self._fail_soon(str(exc))
            return

        self._estimate_timer.stop()
        self._exporting = True
        self._estimating = False
        self._sync_buttons()
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status_label.setText("正在生成 PDF…")

        signature = self._signature()
        plan = self._cached_plan if self._cached_signature == signature else None
        job = ExportJob(self.queue.paths(), settings, output_path, plan)
        job.progress.connect(self._on_progress)
        job.succeeded.connect(self._on_exported)
        job.failed.connect(self._on_export_failed)
        job.cancelled.connect(self._on_export_cancelled)
        self._runner.start(job)

    def current_settings(self) -> ExportSettings:
        return ExportSettings(
            page=str(self.page_combo.currentData()),
            dpi=self.dpi_spin.value(),
            max_long_edge=self.edge_spin.value(),
            jpeg_quality=self.quality_spin.value(),
            margin_mm=float(self.margin_spin.value()),
            grayscale=self.grayscale_check.isChecked(),
            auto_orient=self.orient_check.isChecked(),
            sizing=str(self.sizing_combo.currentData()),
            target_mb=float(self.target_spin.value()),
        ).clamped()

    def save_settings(self) -> None:
        settings = self.current_settings()
        store = self._store
        store.setValue("page", settings.page)
        store.setValue("dpi", settings.dpi)
        store.setValue("max_long_edge", settings.max_long_edge)
        store.setValue("jpeg_quality", settings.jpeg_quality)
        store.setValue("margin_mm", settings.margin_mm)
        store.setValue("grayscale", settings.grayscale)
        store.setValue("auto_orient", settings.auto_orient)
        store.setValue("sizing", settings.sizing)
        store.setValue("target_mb", settings.target_mb)
        store.setValue("preset", self.preset_combo.currentData())
        store.setValue("last_dir", self._last_dir)

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        left = QFrame()
        left.setObjectName("card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 12)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._build_toolbar())
        left_layout.addWidget(self.queue, 1)
        self.count_label = QLabel("还没有图片")
        self.count_label.setObjectName("footer")
        left_layout.addWidget(self.count_label)

        right = self._build_settings()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([760, 400])
        root.addWidget(splitter)

        QShortcut(QKeySequence.StandardKey.Open, self, self._choose_files)
        QShortcut(QKeySequence.StandardKey.Save, self, self._choose_output)
        for sequence in (QKeySequence.StandardKey.Delete, QKeySequence(Qt.Key.Key_Backspace)):
            shortcut = QShortcut(sequence, self.queue.list)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._remove_selected)

    def _build_toolbar(self) -> QWidget:
        self.toolbar = QWidget()
        layout = QVBoxLayout(self.toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.add_button = self._tool_button("添加图片", self._choose_files)
        self.folder_button = self._tool_button("添加文件夹", self._choose_folder)
        self.up_button = self._tool_button("上移", lambda: self._move(-1))
        self.down_button = self._tool_button("下移", lambda: self._move(1))
        self.remove_button = self._tool_button("移除", self._remove_selected)
        self.clear_button = self._tool_button("清空", self._clear)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.add_button)
        top.addWidget(self.folder_button)
        top.addStretch(1)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self.up_button)
        bottom.addWidget(self.down_button)
        bottom.addWidget(self.remove_button)
        bottom.addWidget(self.clear_button)
        bottom.addStretch(1)
        layout.addLayout(top)
        layout.addLayout(bottom)
        return self.toolbar

    def _build_settings(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumWidth(340)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #fffcf7; border: none; }")
        scroll.viewport().setStyleSheet("background: #fffcf7; border: none;")
        self.form = QWidget()
        form_layout = QVBoxLayout(self.form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        form_layout.addWidget(self._section("页面"))
        self.page_combo = self._combo(PAGE_CHOICES)
        form_layout.addWidget(self.page_combo)
        self.orient_check = QCheckBox("横图自动换成横向页面")
        self.orient_check.setChecked(True)
        form_layout.addWidget(self.orient_check)
        self.margin_row, self.margin_spin = self._double_row("页边距", 0, 30, 1, " mm")
        self.margin_spin.setValue(8)
        form_layout.addWidget(self.margin_row)

        form_layout.addSpacing(6)
        form_layout.addWidget(self._section("压缩"))
        self.sizing_combo = self._combo(SIZING_CHOICES)
        form_layout.addWidget(self.sizing_combo)
        self.preset_combo = self._combo(PRESET_CHOICES)
        form_layout.addWidget(self.preset_combo)

        self.dpi_row, self.dpi_caption, self.dpi_slider, self.dpi_spin = self._slider_row(
            "分辨率", MIN_DPI, MAX_DPI, " DPI"
        )
        self.edge_row, self.edge_caption, self.edge_slider, self.edge_spin = self._slider_row(
            "最长边", MIN_EDGE, MAX_EDGE, " px"
        )
        self.quality_row, self.quality_caption, self.quality_slider, self.quality_spin = self._slider_row(
            "JPEG 质量", MIN_JPEG_QUALITY, MAX_JPEG_QUALITY, ""
        )
        self.dpi_spin.setValue(150)
        self.edge_spin.setValue(1920)
        self.quality_spin.setValue(75)
        form_layout.addWidget(self.dpi_row)
        form_layout.addWidget(self.edge_row)
        form_layout.addWidget(self.quality_row)

        self.target_row, self.target_spin = self._double_row(
            "目标大小", MIN_TARGET_MB, MAX_TARGET_MB, 1, " MB"
        )
        self.target_spin.setValue(5)
        self.target_spin.setSingleStep(0.5)
        form_layout.addWidget(self.target_row)

        self.grayscale_check = QCheckBox("转为黑白")
        form_layout.addWidget(self.grayscale_check)
        scroll.setWidget(self.form)
        outer.addWidget(scroll, 1)

        self.estimate_label = QLabel("添加图片后会估算 PDF 体积")
        self.estimate_label.setObjectName("estimate")
        self.estimate_label.setWordWrap(True)
        self.hint_label = QLabel("边长减半，体积大约降到原来的四分之一。")
        self.hint_label.setObjectName("hint")
        self.hint_label.setWordWrap(True)
        self.help_button = QPushButton("查看压缩说明")
        self.help_button.setObjectName("quiet")
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        outer.addWidget(self.estimate_label)
        outer.addWidget(self.hint_label)
        outer.addWidget(self.help_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        outer.addWidget(self.progress)

        button_row = QWidget()
        buttons = QHBoxLayout(button_row)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        self.export_button = QPushButton("生成 PDF")
        self.export_button.setObjectName("primary")
        self.export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_button.setMinimumHeight(44)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.hide()
        buttons.addWidget(self.export_button, 1)
        buttons.addWidget(self.cancel_button)
        outer.addWidget(button_row)

        self.status_label = QLabel("把图片拖进来，或点击添加")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        return card

    def _bind(self) -> None:
        self.queue.files_dropped.connect(self.add_paths)
        self.queue.add_clicked.connect(self._choose_files)
        self.queue.changed.connect(self._on_queue_changed)
        self.queue.order_changed.connect(self._on_order_changed)
        self.page_combo.currentIndexChanged.connect(self._on_option_changed)
        self.sizing_combo.currentIndexChanged.connect(self._on_option_changed)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.dpi_spin.valueChanged.connect(self._on_params_changed)
        self.edge_spin.valueChanged.connect(self._on_params_changed)
        self.quality_spin.valueChanged.connect(self._on_params_changed)
        self.margin_spin.valueChanged.connect(self._on_option_changed)
        self.target_spin.valueChanged.connect(self._on_option_changed)
        self.grayscale_check.toggled.connect(self._on_option_changed)
        self.orient_check.toggled.connect(self._on_option_changed)
        self.help_button.clicked.connect(self._show_help)
        self.export_button.clicked.connect(self._choose_output)
        self.cancel_button.clicked.connect(self._cancel_job)
        self._runner.idle.connect(self._on_runner_idle)

    def _load_settings(self) -> None:
        self._applying += 1
        try:
            self._select(self.page_combo, self._read_str("page", "a4"))
            self._select(self.sizing_combo, self._read_str("sizing", "manual"))
            self._select(self.preset_combo, self._read_str("preset", "standard"))
            self.dpi_spin.setValue(self._read_int("dpi", 150))
            self.edge_spin.setValue(self._read_int("max_long_edge", 1920))
            self.quality_spin.setValue(self._read_int("jpeg_quality", 75))
            self.margin_spin.setValue(self._read_float("margin_mm", 8.0))
            self.target_spin.setValue(self._read_float("target_mb", 5.0))
            self.grayscale_check.setChecked(self._read_bool("grayscale", False))
            self.orient_check.setChecked(self._read_bool("auto_orient", True))
            self._last_dir = self._read_str("last_dir", str(Path.home()))
        finally:
            self._applying -= 1

    def _on_queue_changed(self) -> None:
        self._cached_plan = None
        self._cached_signature = None
        self._update_count()
        self._sync_buttons()
        if self.queue.count() == 0:
            self._estimate_timer.stop()
            self.estimate_label.setText("添加图片后会估算 PDF 体积")
            self._set_warn(False)
            return
        self._schedule_estimate()

    def _on_order_changed(self) -> None:
        self._cached_plan = None
        self._cached_signature = None

    def _on_option_changed(self) -> None:
        if self._applying or not self._alive:
            return
        self._sync_mode()
        self.save_settings()
        self._schedule_estimate()

    def _on_params_changed(self) -> None:
        if self._applying or not self._alive:
            return
        self._mark_custom_if_needed()
        self.save_settings()
        self._schedule_estimate()

    def _on_preset_changed(self) -> None:
        if self._applying or not self._alive:
            return
        key = self.preset_combo.currentData()
        if key in PRESETS:
            self._apply_preset(key)
        self.save_settings()
        self._schedule_estimate()

    def _apply_preset(self, key: str) -> None:
        preset = PRESETS[key]
        self._applying += 1
        try:
            self.dpi_spin.setValue(preset.dpi)
            self.edge_spin.setValue(preset.max_long_edge)
            self.quality_spin.setValue(preset.jpeg_quality)
        finally:
            self._applying -= 1

    def _mark_custom_if_needed(self) -> None:
        key = self.preset_combo.currentData()
        if key not in PRESETS:
            return
        preset = PRESETS[key]
        same = (
            self.dpi_spin.value() == preset.dpi
            and self.edge_spin.value() == preset.max_long_edge
            and self.quality_spin.value() == preset.jpeg_quality
        )
        if same:
            return
        self._applying += 1
        try:
            self._select(self.preset_combo, "custom")
        finally:
            self._applying -= 1

    def _sync_mode(self) -> None:
        original = self.page_combo.currentData() == "original"
        target = self.sizing_combo.currentData() == "target"
        self.edge_row.setVisible(original)
        self.dpi_row.setVisible(not original)
        self.margin_row.setVisible(not original)
        self.orient_check.setVisible(not original)
        self.target_row.setVisible(target)
        self.dpi_caption.setText("分辨率上限" if target else "分辨率")
        self.edge_caption.setText("最长边上限" if target else "最长边")
        self.quality_caption.setText("质量上限" if target else "JPEG 质量")

    def _schedule_estimate(self) -> None:
        if self._exporting or self.queue.count() == 0:
            return
        self._cached_plan = None
        self._cached_signature = None
        self.status_label.setText("正在估算体积…")
        self._estimate_timer.start()

    def _start_estimate(self) -> None:
        if not self._alive or self._exporting or self.queue.count() == 0:
            return
        self._estimating = True
        self._sync_buttons()
        self.progress.show()
        self.progress.setRange(0, 0)
        job = EstimateJob(self.queue.paths(), self.current_settings())
        signature = self._signature()
        job.progress.connect(self._on_progress)
        job.succeeded.connect(lambda plan, sig=signature: self._on_estimated(plan, sig))
        job.failed.connect(self._on_estimate_failed)
        job.cancelled.connect(self._on_estimate_cancelled)
        self._runner.start(job)

    def _choose_files(self) -> None:
        paths, _selected = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            self._last_dir,
            image_dialog_filter(),
        )
        if not paths:
            return
        self._last_dir = str(Path(paths[0]).parent)
        self.add_paths(paths)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文件夹", self._last_dir)
        if not path:
            return
        self._last_dir = path
        self.add_paths([path])

    def _choose_output(self) -> None:
        if self.queue.count() == 0 or self._exporting:
            return
        default = str(Path(self._last_dir) / "图片.pdf")
        path, _selected = QFileDialog.getSaveFileName(self, "保存 PDF", default, "PDF (*.pdf)")
        if not path:
            return
        if Path(path).suffix.lower() != ".pdf":
            path += ".pdf"
        self._last_dir = str(Path(path).parent)
        self.export_to(path)

    def _move(self, delta: int) -> None:
        if not self.queue.move_current(delta):
            self.status_label.setText("请先选中要移动的图片")

    def _remove_selected(self) -> None:
        removed = self.queue.remove_selected()
        if removed:
            self.status_label.setText(f"已移除 {removed} 张")
        else:
            self.status_label.setText("请先选中要移除的图片")

    def _clear(self) -> None:
        if self.queue.count() == 0:
            return
        self.queue.clear_images()
        self.status_label.setText("已清空列表")

    def _cancel_job(self) -> None:
        self._runner.cancel()
        self.status_label.setText("已取消")

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if not self._alive:
            return
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)
        self.progress.show()
        self.status_label.setText(message)

    def _on_estimated(self, plan: object, signature: tuple) -> None:
        if not self._alive or self._exporting:
            return
        if signature != self._signature():
            return
        if not isinstance(plan, Plan):
            return
        self._estimating = False
        self._cached_signature = signature
        self._cached_plan = plan
        self._show_plan(plan)
        self.progress.hide()
        self.status_label.setText("可以生成 PDF")
        self._sync_buttons()

    def _on_estimate_failed(self, message: str) -> None:
        if not self._alive or self._exporting:
            return
        self._estimating = False
        self.progress.hide()
        self.estimate_label.setText(message)
        self._set_warn(True)
        self.status_label.setText("估算失败")
        self._sync_buttons()

    def _on_estimate_cancelled(self) -> None:
        if not self._alive or self._exporting:
            return
        self._estimating = False
        self._sync_buttons()

    def _on_exported(self, outcome: object) -> None:
        if not self._alive or not isinstance(outcome, ExportOutcome):
            return
        self._exporting = False
        self.progress.hide()
        self._sync_buttons()
        self._last_dir = str(Path(outcome.output_path).parent)
        self.save_settings()
        self.status_label.setText(f"已保存 {format_bytes(outcome.output_bytes)}")
        self.export_succeeded.emit(outcome)
        if self.show_result_dialog:
            self._show_done_dialog(outcome)

    def _on_export_failed(self, message: str) -> None:
        if not self._alive:
            return
        self._exporting = False
        self.progress.hide()
        self._sync_buttons()
        self.status_label.setText(message)
        self.export_failed.emit(message)
        if self.show_result_dialog:
            QMessageBox.warning(self, "没有生成 PDF", message)

    def _on_export_cancelled(self) -> None:
        if not self._alive:
            return
        self._exporting = False
        self.progress.hide()
        self._sync_buttons()
        self.status_label.setText("已取消")
        self.export_cancelled.emit()

    def _on_runner_idle(self) -> None:
        if not self._alive:
            return
        if not self._exporting:
            self._estimating = False
            self.progress.hide()
            self._sync_buttons()

    def _show_plan(self, plan: Plan) -> None:
        approx = approximate_pdf_size(plan.jpeg_bytes, plan.page_count)
        line = f"约 {format_bytes(approx)}"
        if plan.source_bytes > 0:
            ratio = approx / plan.source_bytes
            if ratio > 1.05:
                line += "。原图已经很小，PDF 不会比它们更小"
            else:
                line += f"，约为原图的 {ratio * 100:.0f}%"
        lines = [line, plan.note]
        if not plan.hit_target:
            lines.append("目标体积偏小，结果仍会大于目标。")
        self.estimate_label.setText("\n".join(lines))
        self._set_warn(not plan.hit_target)

    def _show_done_dialog(self, outcome: ExportOutcome) -> None:
        box = QMessageBox(self)
        box.setIcon(
            QMessageBox.Icon.Information if outcome.hit_target else QMessageBox.Icon.Warning
        )
        box.setWindowTitle("PDF 已生成")
        ratio = ""
        if outcome.source_bytes:
            ratio = f"，约为原图的 {outcome.output_bytes / outcome.source_bytes * 100:.0f}%"
        box.setText(f"已保存 {outcome.page_count} 页，{format_bytes(outcome.output_bytes)}{ratio}")
        box.setInformativeText(f"{outcome.note}\n\n{outcome.output_path}")
        reveal = None
        if sys.platform == "darwin":
            reveal = box.addButton("在 Finder 中显示", QMessageBox.ButtonRole.ActionRole)
        box.addButton("好", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if reveal is not None and box.clickedButton() is reveal:
            subprocess.run(["open", "-R", outcome.output_path], check=False)

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("体积是怎么控制的")
        dialog.resize(520, 560)
        layout = QVBoxLayout(dialog)
        label = QLabel(ALGORITHM_HELP)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _update_count(self) -> None:
        count = self.queue.count()
        if count == 0:
            self.count_label.setText("还没有图片")
            return
        self.count_label.setText(f"共 {count} 张 · 原始 {format_bytes(self.queue.total_bytes())}")

    def _sync_buttons(self) -> None:
        has_images = self.queue.count() > 0
        editing = not self._exporting
        self.export_button.setEnabled(has_images and editing)
        self.cancel_button.setVisible(self._exporting or self._estimating)
        self.cancel_button.setEnabled(True)
        self.toolbar.setEnabled(editing)
        self.queue.set_interaction_enabled(editing)
        for widget in (
            self.page_combo,
            self.orient_check,
            self.margin_row,
            self.sizing_combo,
            self.preset_combo,
            self.dpi_row,
            self.edge_row,
            self.quality_row,
            self.target_row,
            self.grayscale_check,
        ):
            widget.setEnabled(editing)

    def _signature(self) -> tuple:
        items = []
        for path in self.queue.paths():
            try:
                stat = os.stat(path)
                items.append((path, stat.st_mtime_ns, stat.st_size))
            except OSError:
                items.append((path, 0, 0))
        return (tuple(items), self.current_settings())

    def _fail_soon(self, message: str) -> None:
        QTimer.singleShot(0, lambda message=message: self.export_failed.emit(message))

    def _set_warn(self, warn: bool) -> None:
        self.estimate_label.setProperty("warn", warn)
        self.estimate_label.style().unpolish(self.estimate_label)
        self.estimate_label.style().polish(self.estimate_label)

    def _read_str(self, key: str, default: str) -> str:
        value = self._store.value(key, default)
        return default if value is None else str(value)

    def _read_int(self, key: str, default: int) -> int:
        try:
            return int(self._store.value(key, default))
        except (TypeError, ValueError):
            return default

    def _read_float(self, key: str, default: float) -> float:
        try:
            return float(self._store.value(key, default))
        except (TypeError, ValueError):
            return default

    def _read_bool(self, key: str, default: bool) -> bool:
        value = self._store.value(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        return bool(value)

    @staticmethod
    def _select(combo: QComboBox, key: str) -> None:
        index = combo.findData(key)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    @staticmethod
    def _combo(choices: tuple[tuple[str, str], ...]) -> QComboBox:
        combo = QComboBox()
        for key, label in choices:
            combo.addItem(label, key)
        return combo

    @staticmethod
    def _tool_button(text: str, handler) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(handler)
        return button

    @staticmethod
    def _slider_row(
        caption: str, low: int, high: int, suffix: str
    ) -> tuple[QWidget, QLabel, QSlider, QSpinBox]:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel(caption)
        label.setMinimumWidth(88)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setFixedWidth(96)
        layout.addWidget(label)
        layout.addWidget(slider, 1)
        layout.addWidget(spin)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        return row, label, slider, spin

    @staticmethod
    def _double_row(
        caption: str, low: float, high: float, decimals: int, suffix: str
    ) -> tuple[QWidget, QDoubleSpinBox]:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel(caption)
        label.setMinimumWidth(88)
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(spin)
        return row, spin
