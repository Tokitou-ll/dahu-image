# Dahu Image

[中文](README.md)

Dahu Image is a PySide6 desktop tool for working with images and PDFs. The current feature merges several images into one PDF and controls the file size with resolution and JPEG quality. The window text is in Chinese.

Python 3.12 or newer is required. Dependencies are listed in `requirements.txt`: PySide6, Pillow, img2pdf, and pillow-heif.

## Run

The repository already contains a `venv`. From the project root:

```bash
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

## Images to PDF

Drop images onto the window, or use 添加图片 (Add Images) and 添加文件夹 (Add Folder). A folder contributes only the files in that directory. Drag pages to reorder them, or use 上移 and 下移. Choose the settings, then click 生成 PDF.

Supported formats are PNG, JPG, WEBP, BMP, TIFF, GIF, HEIC, and HEIF. Transparency is flattened onto white, orientation is taken from the photo, and an animation keeps its first frame. Small images are not enlarged.

The panel on the right controls:

- Page: A4, Letter, or the original aspect ratio. Fixed pages have a margin, and landscape photos can switch to a landscape page.
- Compression: manual settings, or a target file size. Presets are Small, Standard, High, and Print. Custom values are available too.
- In manual mode, a fixed page uses DPI, the original-ratio mode uses the longest edge, and both use a JPEG quality.
- In target-size mode, those resolution and quality values are ceilings. The program searches within them for settings that fit the target.

Shortcuts: Cmd/Ctrl+O opens files, and Cmd/Ctrl+S saves. Delete or Backspace on the image list removes the selected images.

## How the file gets smaller

The PDF is about as large as the JPEG embedded on each page. Each image is compressed once:

1. **Reduce the resolution first.** For A4 or Letter, the pixel limit is the printable page size multiplied by the DPI. For the original aspect ratio, only the longest edge is limited. Images are scaled down proportionally. Halving an edge leaves about a quarter of the pixels, and that is the main size control.
2. **Encode JPEG second.** Higher quality stays clearer. 90 and above keep full color and suit printing. 75 to 89 merge a little color. Below that, stronger chroma subsampling makes a smaller file.
3. Those JPEG bytes are embedded in the PDF as they are. They are not compressed again.

Target size first searches, at the resolution ceiling, for the highest JPEG quality that fits. If the lowest quality is still too large, the resolution is reduced until the file fits, or until the readable floor is reached: quality 35 and about 40% of the resolution ceiling. If the floor is still above the target, the program writes the smallest file it is allowed to produce and says so.

The same explanation is available in the app under 查看压缩说明.

## Layout

- `shared/domain` reads images, scales them, encodes JPEG, and collects file names. It does not depend on the interface.
- `shared/presentation` holds the window, styles, image queue, and background jobs shared by features.
- `features/<name>` holds one feature's settings, processing, and page. The current feature is `features/image_to_pdf`.
- `main.py` registers features and starts the app.
- `version.py` holds the version.

To add a feature, create a package under `features`, register it in `main.py`, and add the package name to `pyproject.toml`. Existing features stay as they are.

## Tests

```bash
./venv/bin/python -m unittest discover -s tests -q
```

## License

This program is released under the [GNU GPL v3](LICENSE).
