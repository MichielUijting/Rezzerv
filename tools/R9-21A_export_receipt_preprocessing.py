from __future__ import annotations

import argparse
import io
import os
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps
from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore


def _load_bytes(input_path: Path, member: str | None) -> tuple[bytes, str]:
    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path, "r") as archive:
            names = archive.namelist()
            selected = member or next((name for name in names if Path(name).name.lower() == "ah foto 3.jpg"), None)
            if not selected:
                raise SystemExit("Geen bestand gekozen en AH foto 3.jpg niet gevonden in zip.")
            return archive.read(selected), Path(selected).name
    return input_path.read_bytes(), input_path.name


def _save_pil(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"R9-21L write verification failed: {path}")


def _deskew_pil(image: Image.Image) -> Image.Image:
    if cv2 is None or np is None:
        return image
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
    angles: list[float] = []
    if lines is not None:
        for line in lines[:40]:
            _rho, theta = line[0]
            angle = float(np.degrees(theta) - 90)
            while angle <= -90:
                angle += 180
            while angle > 90:
                angle -= 180
            if abs(angle) <= 45:
                angles.append(angle)
    if not angles:
        return image
    angle = sorted(angles)[len(angles) // 2]
    if abs(angle) < 0.5:
        return image
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(arr, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))


def _hard_reset_case_dir(case_dir: Path) -> None:
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)


def _file_line(path: Path) -> str:
    stat = path.stat()
    return f"{path.name}|bytes={stat.st_size}|mtime={datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}"


def export_debug(input_path: Path, member: str | None, out_dir: Path) -> Path:
    run_started = datetime.now().isoformat(timespec="seconds")
    data, filename = _load_bytes(input_path, member)
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image).convert("RGB")

    case_dir = out_dir / Path(filename).stem.replace(" ", "_")
    _hard_reset_case_dir(case_dir)

    written: list[Path] = []

    p = case_dir / "01_original.png"
    _save_pil(image, p)
    written.append(p)

    rotated_90 = image
    if image.width > image.height:
        rotated_90 = image.rotate(90, expand=True)
    p = case_dir / "02_rotated_90_if_landscape.png"
    _save_pil(rotated_90, p)
    written.append(p)

    os.environ['REZZERV_RECEIPT_PREPROCESS_DEBUG_DIR'] = str(case_dir / '99_preprocess_checkpoints')
    runtime_bytes, runtime_decision = apply_receipt_image_preprocessing(data, filename)
    runtime_image = Image.open(io.BytesIO(runtime_bytes)).convert("RGB")
    p = case_dir / "03_runtime_preprocessed.png"
    _save_pil(runtime_image, p)
    written.append(p)

    deskewed = _deskew_pil(rotated_90)
    p = case_dir / "03_deskewed.png"
    _save_pil(deskewed, p)
    written.append(p)

    # R9-21L: OCR grayscale follows the actual runtime preprocessing output,
    # not the old deskew-only image.
    gray = ImageOps.grayscale(runtime_image)
    p = case_dir / "04_ocr_input_grayscale.png"
    _save_pil(gray, p)
    written.append(p)

    manifest = case_dir / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"run_started={run_started}",
                f"input={input_path}",
                f"member={member or filename}",
                f"original_size={image.width}x{image.height}",
                f"rotated_size={rotated_90.width}x{rotated_90.height}",
                f"runtime_size={runtime_image.width}x{runtime_image.height}",
                f"output_dir={case_dir}",
                f"runtime_decision={runtime_decision.to_dict()}",
                f"diagnostics={runtime_decision.to_dict().get('diagnostics')}",
                "written_files:",
                *[f"- {_file_line(path)}" for path in written],
                "",
            ]
        ),
        encoding="utf-8",
    )

    now = time.time()
    for idx, path in enumerate([*written, manifest]):
        os.utime(path, (now + idx, now + idx))

    return case_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="R9-21L hard-reset visual receipt preprocessing export.")
    parser.add_argument("input", help="Image path or zip path")
    parser.add_argument("--member", default=None, help='Optional zip member name, for example "AH foto 3.jpg"')
    parser.add_argument("--out", default="tools/debug_output/R9-21A_preprocessing", help="Output directory")
    args = parser.parse_args()
    out = export_debug(Path(args.input), args.member, Path(args.out))
    print(f"R9-21L preprocessing export hard-reset geschreven naar: {out}")
    for item in sorted(out.iterdir()):
        print(f"{item.name}\t{item.stat().st_size} bytes")


if __name__ == "__main__":
    main()
