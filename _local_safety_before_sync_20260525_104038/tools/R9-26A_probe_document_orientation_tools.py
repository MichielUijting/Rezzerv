from __future__ import annotations

import argparse
import io
import json
import math
import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


def _load_bytes(input_path: Path, member: str | None) -> tuple[bytes, str]:
    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path, "r") as archive:
            names = archive.namelist()
            selected = member or next((name for name in names if Path(name).name.lower() == "ah foto 3.jpg"), None)
            if not selected:
                raise SystemExit("Geen bestand gekozen en AH foto 3.jpg niet gevonden in zip.")
            return archive.read(selected), Path(selected).name
    return input_path.read_bytes(), input_path.name


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _safe_name(filename: str) -> str:
    return Path(filename).stem.replace(" ", "_")


def _rembg_neutralized(file_bytes: bytes, manifest: dict[str, Any]) -> Image.Image:
    original = Image.open(io.BytesIO(file_bytes))
    original = ImageOps.exif_transpose(original).convert("RGB")
    manifest["original_size"] = [original.width, original.height]

    if rembg_remove is None:
        manifest["rembg"] = {"available": False}
        return original

    try:
        rgba_bytes = rembg_remove(file_bytes)
        rgba = Image.open(io.BytesIO(rgba_bytes)).convert("RGBA")
        rgba = ImageOps.exif_transpose(rgba)
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        neutralized = Image.alpha_composite(white, rgba).convert("RGB")
        manifest["rembg"] = {"available": True, "route": "white_background_composite", "size": [neutralized.width, neutralized.height]}
        return neutralized
    except Exception as exc:
        manifest["rembg"] = {"available": True, "error": f"{type(exc).__name__}: {exc}"}
        return original


def _basic_portrait_candidate(image: Image.Image, manifest: dict[str, Any]) -> Image.Image:
    candidate = image
    if image.width > image.height:
        candidate = image.rotate(90, expand=True)
        manifest["basic_portrait"] = {"rotated_90": True, "size": [candidate.width, candidate.height]}
    else:
        manifest["basic_portrait"] = {"rotated_90": False, "size": [candidate.width, candidate.height]}
    return candidate


def _hough_textline_angle(gray) -> tuple[float | None, dict[str, Any]]:
    if cv2 is None or np is None:
        return None, {"available": False}

    # Detect text/receipt line direction, not white canvas.
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=max(80, gray.shape[1] // 12), maxLineGap=20)

    if lines is None:
        return None, {"available": True, "lines": 0}

    angles: list[float] = []
    for item in lines[:300]:
        x1, y1, x2, y2 = item[0]
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        while angle <= -90:
            angle += 180
        while angle > 90:
            angle -= 180

        # Receipt text baselines are near horizontal after correction.
        if abs(angle) <= 45:
            angles.append(float(angle))

    if not angles:
        return None, {"available": True, "lines": int(len(lines)), "usable_angles": 0}

    angles_sorted = sorted(angles)
    median = angles_sorted[len(angles_sorted) // 2]
    return median, {"available": True, "lines": int(len(lines)), "usable_angles": len(angles), "median_angle": median}


def _rotate_bound(image: Image.Image, angle: float) -> Image.Image:
    if cv2 is None or np is None:
        return image.rotate(angle, expand=True, fillcolor=(255, 255, 255))

    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2.0) - (w / 2.0)
    matrix[1, 2] += (new_h / 2.0) - (h / 2.0)
    rotated = cv2.warpAffine(arr, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))


def _hough_candidate(image: Image.Image, manifest: dict[str, Any]) -> Image.Image:
    if cv2 is None or np is None:
        manifest["hough_textline"] = {"available": False}
        return image

    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    angle, info = _hough_textline_angle(gray)
    manifest["hough_textline"] = info

    if angle is None:
        return image

    # If text baseline is +angle, rotate by -angle.
    candidate = _rotate_bound(image, -angle)
    if candidate.width > candidate.height:
        candidate = candidate.rotate(90, expand=True, fillcolor=(255, 255, 255))
        manifest["hough_textline"]["post_rotated_to_portrait"] = True
    else:
        manifest["hough_textline"]["post_rotated_to_portrait"] = False

    manifest["hough_textline"]["applied_rotation"] = -angle
    manifest["hough_textline"]["output_size"] = [candidate.width, candidate.height]
    return candidate


def _paddle_probe_available(manifest: dict[str, Any]) -> None:
    result: dict[str, Any] = {}
    for module in ["paddleocr", "paddle", "paddlex"]:
        try:
            proc = subprocess.run(
                ["python", "-c", f"import {module}; print('ok')"],
                text=True,
                capture_output=True,
                timeout=20,
            )
            result[module] = {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()[-500:]}
        except Exception as exc:
            result[module] = {"error": f"{type(exc).__name__}: {exc}"}
    manifest["paddle_probe"] = result


def export_probe(input_path: Path, member: str | None, out_dir: Path) -> Path:
    data, filename = _load_bytes(input_path, member)
    case_dir = out_dir / _safe_name(filename)
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_started": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_path),
        "member": member or filename,
        "goal": "R9-26A orientation probe: rembg + public/proven orientation routes, no runtime integration",
    }

    rembg_img = _rembg_neutralized(data, manifest)
    _save(rembg_img, case_dir / "01_rembg_neutralized.png")

    basic = _basic_portrait_candidate(rembg_img, manifest)
    _save(basic, case_dir / "10_basic_portrait_candidate.png")

    hough = _hough_candidate(rembg_img, manifest)
    _save(hough, case_dir / "20_hough_textline_attempt.png")

    # Best candidate for now: Hough when it has usable angles, otherwise basic portrait.
    if manifest.get("hough_textline", {}).get("usable_angles", 0):
        best = hough
        manifest["best_candidate"] = {"route": "hough_textline_attempt"}
    else:
        best = basic
        manifest["best_candidate"] = {"route": "basic_portrait_candidate"}

    _save(best, case_dir / "30_best_candidate.png")
    gray = ImageOps.grayscale(best)
    _save(gray, case_dir / "40_best_candidate_grayscale.png")

    _paddle_probe_available(manifest)

    manifest["files"] = sorted(p.name for p in case_dir.iterdir())
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (case_dir / "manifest.txt").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return case_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="R9-26A probe document orientation tools after rembg.")
    parser.add_argument("input")
    parser.add_argument("--member", default=None)
    parser.add_argument("--out", default="/tmp/R9-26A_orientation_probe")
    args = parser.parse_args()

    out = export_probe(Path(args.input), args.member, Path(args.out))
    print(f"R9-26A orientation probe geschreven naar: {out}")
    for item in sorted(out.iterdir()):
        print(f"{item.name}\t{item.stat().st_size} bytes")


if __name__ == "__main__":
    main()
