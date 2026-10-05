"""界面能添加图片、调节参数，并在后台写出 PDF。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from features.image_to_pdf.feature import ImageToPdfFeature
from shared.presentation.shell.main_window import MainWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ini = str(Path(self.tmp.name) / "settings.ini")
        self.settings = QSettings(ini, QSettings.Format.IniFormat)
        self.window = MainWindow(self.settings, [ImageToPdfFeature()])
        self.page = self.window.page_for("image_to_pdf")
        self.page.show_result_dialog = False

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_add_reorder_remove_and_presets(self) -> None:
        paths = []
        for name in ("a.png", "b.png", "c.png"):
            path = Path(self.tmp.name) / name
            Image.new("RGB", (40, 30), (10, 20, 30)).save(path)
            paths.append(str(path))
        message = self.page.add_paths(paths)
        self.assertIn("已添加 3 张", message)
        self.assertEqual([Path(path).name for path in self.page.queue.paths()], ["a.png", "b.png", "c.png"])

        again = self.page.add_paths([paths[0]])
        self.assertIn("已在列表中", again)
        self.assertEqual(self.page.queue.count(), 3)

        self.page.queue.list.setCurrentRow(2)
        self.assertTrue(self.page.queue.move_current(-1))
        self.assertEqual([Path(path).name for path in self.page.queue.paths()], ["a.png", "c.png", "b.png"])

        self.page.queue.list.clearSelection()
        self.page.queue.list.setCurrentRow(0)
        self.page._remove_selected()
        self.assertEqual(self.page.queue.count(), 2)

        self.page.preset_combo.setCurrentIndex(self.page.preset_combo.findData("small"))
        self.assertEqual(self.page.dpi_spin.value(), 96)
        self.assertEqual(self.page.edge_spin.value(), 1280)
        self.assertEqual(self.page.quality_spin.value(), 60)
        self.page.quality_spin.setValue(61)
        self.assertEqual(self.page.preset_combo.currentData(), "custom")

        self.window.show()
        self.app.processEvents()
        self.page.page_combo.setCurrentIndex(self.page.page_combo.findData("original"))
        self.app.processEvents()
        self.assertTrue(self.page.edge_row.isVisible())
        self.assertFalse(self.page.dpi_row.isVisible())
        self.page.sizing_combo.setCurrentIndex(self.page.sizing_combo.findData("target"))
        self.app.processEvents()
        self.assertTrue(self.page.target_row.isVisible())

    def test_export_from_the_window(self) -> None:
        paths = []
        for name, color in (("red.png", (200, 20, 20)), ("blue.png", (20, 20, 200))):
            path = Path(self.tmp.name) / name
            Image.new("RGB", (64, 40), color).save(path)
            paths.append(str(path))
        self.page.add_paths(paths)
        output = Path(self.tmp.name) / "图片.pdf"
        loop = QEventLoop()
        errors: list[str] = []
        self.page.export_succeeded.connect(lambda _outcome: loop.quit())
        self.page.export_failed.connect(lambda message: errors.append(message) or loop.quit())
        self.page.export_cancelled.connect(lambda: errors.append("cancelled") or loop.quit())
        self.page.export_to(str(output))
        QTimer.singleShot(20000, loop.quit)
        loop.exec()
        self.assertEqual(errors, [], errors)
        self.assertTrue(output.exists())
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        self.assertIn("已保存", self.page.status_label.text())

    def test_shell_switches_registered_features(self) -> None:
        marker = QWidget()
        marker.setObjectName("page")

        class Extra:
            id = "extra"
            title = "另一项"

            def create_page(self, settings):
                return marker

            def shutdown_page(self, page) -> None:
                page.shut_down = True

        window = MainWindow(self.settings, [ImageToPdfFeature(), Extra()])
        self.addCleanup(window.close)
        self.assertEqual(
            [button.text() for button in window.findChildren(QPushButton) if button.objectName().startswith("nav")],
            ["图片转 PDF", "另一项"],
        )
        self.assertIs(window.current_page(), window.page_for("image_to_pdf"))
        window.show_feature("extra")
        self.assertIs(window.current_page(), marker)
        names = [
            button.objectName()
            for button in window.findChildren(QPushButton)
            if button.objectName().startswith("nav")
        ]
        self.assertEqual(names, ["navItem", "navCurrent"])


if __name__ == "__main__":
    unittest.main()
