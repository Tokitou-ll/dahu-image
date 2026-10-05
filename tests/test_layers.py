"""分层约束：领域代码不碰界面，窗口壳不引用具体功能。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def sources(*relative_dirs: str) -> list[Path]:
    files: list[Path] = []
    for relative in relative_dirs:
        files.extend(sorted((ROOT / relative).rglob("*.py")))
    return files


class LayerTests(unittest.TestCase):
    def test_domain_stays_free_of_ui_and_features(self) -> None:
        forbidden = ("PySide6", "img2pdf", "features", "shared.presentation")
        for path in sources("shared/domain"):
            self._assert_clean(path, forbidden)

    def test_pdf_flow_stays_free_of_ui(self) -> None:
        forbidden = (
            "PySide6",
            "shared.presentation",
            "features.image_to_pdf.page",
            "features.image_to_pdf.jobs",
            "features.image_to_pdf.feature",
        )
        files = [
            ROOT / "features/image_to_pdf/service.py",
            ROOT / "features/image_to_pdf/settings.py",
            ROOT / "features/image_to_pdf/prepare.py",
        ]
        for path in files:
            self._assert_clean(path, forbidden)

    def test_shared_presentation_does_not_import_features(self) -> None:
        for path in sources("shared/presentation"):
            self._assert_clean(path, ("features",))

    def _assert_clean(self, path: Path, forbidden: tuple[str, ...]) -> None:
        modules = imported_modules(path)
        for name in modules:
            for prefix in forbidden:
                if name == prefix or name.startswith(prefix + "."):
                    self.fail(f"{path.relative_to(ROOT)} imports {name}")


if __name__ == "__main__":
    unittest.main()
