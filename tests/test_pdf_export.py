"""图片压缩和 PDF 生成的行为测试。"""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

import pikepdf
from PIL import Image

from features.image_to_pdf.service import ExportCancelled, plan_pages, write_pdf
from features.image_to_pdf.settings import ExportSettings
from shared.domain.files import collect_inputs
from shared.domain.imaging import load_raster


def noise_image(path: Path, width: int, height: int, seed: int) -> None:
    data = random.Random(seed).randbytes(width * height * 3)
    Image.frombytes("RGB", (width, height), data).save(path, format="PNG")


def pdf_pages(path: Path) -> list[dict]:
    pages = []
    with pikepdf.open(path) as pdf:
        for page in pdf.pages:
            box = page.mediabox
            images = []
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") or {}
            for obj in xobjects.values():
                if str(obj.get("/Subtype")) != "/Image":
                    continue
                images.append(
                    {
                        "w": int(obj["/Width"]),
                        "h": int(obj["/Height"]),
                        "cs": str(obj.get("/ColorSpace")),
                    }
                )
            pages.append(
                {
                    "w": float(box[2]) - float(box[0]),
                    "h": float(box[3]) - float(box[1]),
                    "images": images,
                }
            )
    return pages


def export(paths: list[Path], settings: ExportSettings, output: Path):
    plan = plan_pages([str(path) for path in paths], settings)
    write_pdf(plan.jpeg_pages, settings, output)
    return plan


class PdfExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_exif_orientation_is_applied(self) -> None:
        path = self.root / "turned.jpg"
        image = Image.new("RGB", (400, 200), (180, 20, 20))
        exif = Image.Exif()
        exif[274] = 6
        image.save(path, exif=exif.tobytes())
        raster = load_raster(path, grayscale=False)
        self.assertEqual(raster.size, (200, 400))

    def test_transparency_is_flattened_onto_white(self) -> None:
        path = self.root / "alpha.png"
        image = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
        image.putpixel((0, 0), (0, 0, 255, 255))
        image.save(path)
        output = self.root / "alpha.pdf"
        export([path], ExportSettings(page="original", max_long_edge=1000, jpeg_quality=90), output)
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        raster = load_raster(path, grayscale=False)
        self.assertGreater(raster.getpixel((0, 0))[2], 200)
        self.assertLess(raster.getpixel((0, 0))[0], 40)
        corner = raster.getpixel((3, 3))
        self.assertTrue(all(channel > 245 for channel in corner))

    def test_long_edge_and_page_order(self) -> None:
        wide = self.root / "wide.png"
        tall = self.root / "tall.png"
        Image.new("RGB", (400, 200), (20, 20, 20)).save(wide)
        Image.new("RGB", (100, 300), (20, 20, 200)).save(tall)
        output = self.root / "order.pdf"
        export(
            [wide, tall],
            ExportSettings(page="original", max_long_edge=1000, jpeg_quality=80),
            output,
        )
        pages = pdf_pages(output)
        self.assertEqual(len(pages), 2)
        self.assertEqual((pages[0]["images"][0]["w"], pages[0]["images"][0]["h"]), (400, 200))
        self.assertEqual((pages[1]["images"][0]["w"], pages[1]["images"][0]["h"]), (100, 300))

    def test_small_image_is_not_upscaled(self) -> None:
        path = self.root / "small.png"
        Image.new("RGB", (80, 60), (10, 180, 10)).save(path)
        output = self.root / "small.pdf"
        export([path], ExportSettings(page="original", max_long_edge=1920, jpeg_quality=75), output)
        image = pdf_pages(output)[0]["images"][0]
        self.assertEqual((image["w"], image["h"]), (80, 60))

    def test_a4_downscales_to_dpi_budget(self) -> None:
        path = self.root / "big.png"
        Image.new("RGB", (4000, 3000), (240, 240, 240)).save(path)
        output = self.root / "a4.pdf"
        settings = ExportSettings(
            page="a4",
            dpi=100,
            jpeg_quality=70,
            margin_mm=10,
            auto_orient=False,
        )
        export([path], settings, output)
        page = pdf_pages(output)[0]
        self.assertAlmostEqual(page["w"], 595.28, delta=1)
        self.assertAlmostEqual(page["h"], 841.89, delta=1)
        self.assertGreater(page["h"], page["w"])
        self.assertEqual((page["images"][0]["w"], page["images"][0]["h"]), (748, 561))

    def test_auto_orient_uses_landscape_page(self) -> None:
        path = self.root / "land.png"
        Image.new("RGB", (800, 200), (30, 30, 30)).save(path)
        output = self.root / "land.pdf"
        export(
            [path],
            ExportSettings(page="a4", dpi=100, jpeg_quality=70, margin_mm=8, auto_orient=True),
            output,
        )
        page = pdf_pages(output)[0]
        self.assertGreater(page["w"], page["h"])

    def test_grayscale_uses_gray_colorspace(self) -> None:
        path = self.root / "color.png"
        Image.new("RGB", (120, 80), (200, 40, 40)).save(path)
        output = self.root / "gray.pdf"
        export(
            [path],
            ExportSettings(page="original", max_long_edge=1000, jpeg_quality=70, grayscale=True),
            output,
        )
        colorspace = pdf_pages(output)[0]["images"][0]["cs"]
        self.assertIn("Gray", colorspace)

    def test_lower_quality_and_lower_dpi_make_smaller_files(self) -> None:
        path = self.root / "noise.png"
        noise_image(path, 900, 700, seed=3)
        low = self.root / "low.pdf"
        high = self.root / "high.pdf"
        export([path], ExportSettings(page="original", max_long_edge=900, jpeg_quality=45), low)
        export([path], ExportSettings(page="original", max_long_edge=900, jpeg_quality=90), high)
        self.assertLess(low.stat().st_size, high.stat().st_size)

        screen = self.root / "screen.pdf"
        soft = self.root / "soft.pdf"
        export([path], ExportSettings(page="a4", dpi=72, jpeg_quality=70, margin_mm=0), soft)
        export([path], ExportSettings(page="a4", dpi=200, jpeg_quality=70, margin_mm=0), screen)
        self.assertLess(soft.stat().st_size, screen.stat().st_size)

    def test_target_size_keeps_quality_when_budget_is_large(self) -> None:
        path = self.root / "plain.png"
        Image.new("RGB", (320, 200), (80, 90, 100)).save(path)
        output = self.root / "roomy.pdf"
        plan = export(
            [path],
            ExportSettings(
                page="original",
                max_long_edge=640,
                jpeg_quality=80,
                sizing="target",
                target_mb=20,
            ),
            output,
        )
        self.assertTrue(plan.hit_target)
        self.assertEqual(plan.quality, 80)
        self.assertEqual(plan.scale, 1.0)
        self.assertLess(output.stat().st_size, 20 * 1024 * 1024)

    def test_target_size_shrinks_noisy_pages(self) -> None:
        first = self.root / "n1.png"
        second = self.root / "n2.png"
        noise_image(first, 1000, 800, seed=1)
        noise_image(second, 1000, 800, seed=2)
        output = self.root / "target.pdf"
        target = 0.35 * 1024 * 1024
        plan = export(
            [first, second],
            ExportSettings(
                page="original",
                max_long_edge=1000,
                jpeg_quality=90,
                sizing="target",
                target_mb=0.35,
            ),
            output,
        )
        size = output.stat().st_size
        if plan.hit_target:
            self.assertLessEqual(size, target)
        else:
            self.assertEqual(plan.quality, 35)
            self.assertLessEqual(plan.scale, 0.41)
        self.assertEqual(len(pdf_pages(output)), 2)
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))

    def test_collect_inputs_sorts_folder_and_skips_other_files(self) -> None:
        folder = self.root / "scans"
        folder.mkdir()
        (folder / "sub").mkdir()
        Image.new("RGB", (8, 8), "white").save(folder / "b.jpg")
        Image.new("RGB", (8, 8), "white").save(folder / "a.jpg")
        Image.new("RGB", (8, 8), "white").save(folder / "sub" / "c.jpg")
        (folder / "note.txt").write_text("nope", encoding="utf-8")
        (folder / ".secret.jpg").write_bytes(b"hidden")
        (folder / "empty.png").write_bytes(b"")
        collected = collect_inputs([str(folder), str(self.root / "missing.png")])
        names = [Path(path).name for path in collected.images]
        self.assertEqual(names, ["a.jpg", "b.jpg"])
        self.assertTrue(any(path.endswith("note.txt") for path in collected.skipped))
        self.assertTrue(any(path.endswith("empty.png") for path in collected.skipped))
        self.assertEqual(len(collected.missing), 1)

    def test_unreadable_image_names_the_file(self) -> None:
        path = self.root / "broken.jpg"
        path.write_bytes(b"this is not a jpeg")
        with self.assertRaises(Exception) as caught:
            plan_pages([str(path)], ExportSettings())
        self.assertIn("broken.jpg", str(caught.exception))

    def test_cancel_stops_before_encoding(self) -> None:
        path = self.root / "one.png"
        Image.new("RGB", (32, 32), "white").save(path)

        def cancelled() -> bool:
            return True

        with self.assertRaises(ExportCancelled):
            plan_pages([str(path)], ExportSettings(), is_cancelled=cancelled)


if __name__ == "__main__":
    unittest.main()
