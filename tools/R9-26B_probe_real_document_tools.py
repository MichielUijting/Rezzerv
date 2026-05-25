from __future__ import annotations

import argparse
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

try:
    import numpy as np
except Exception:
    np = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


PROVEN_MODULE_CANDIDATES = [
    "paddleocr",
    "paddle",
    "paddlex",
    "doctr",
    "cv2",
    "skimage",
    "imutils",
]


def _load_bytes(input_path: Path, member: str | None) -> tuple[bytes, str]:
    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path, "r") as archive:
            names = archive.namelist()
            selected = member or next((name for name in names if Path(name).name.lower() == "ah foto 3.jpg"), None)
            if not selected:
                raise SystemExit("Geen bestand gekozen en AH foto 3.jpg niet gevonden in zip.")
            return archive.read(selected), Path(selected).name
    return input_path.read_bytes(), input_path.name


def _safe_stem(filename: str) -> str:
    return Path(filename).stem.replace(" ", "_")


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _run_py_probe(code: str, timeout: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip()[-2000:],
            "stderr": proc.stderr.strip()[-4000:],
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _module_inventory() -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    for name in PROVEN_MODULE_CANDIDATES:
        spec = importlib.util.find_spec(name)
        item: dict[str, Any] = {"available": spec is not None}
        if spec is not None:
            item["origin"] = spec.origin
            version_probe = _run_py_probe(
                f"import {name}; print(getattr({name}, '__version__', 'version_unknown'))",
                timeout=30,
            )
            item["version_probe"] = version_probe
        inventory[name] = item
    return inventory


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


def _write_temp_image(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _probe_paddleocr_orientation(image: Image.Image, case_dir: Path, manifest: dict[str, Any]) -> None:
    """Probe PaddleOCR presence and orientation APIs without integrating runtime.

    Different PaddleOCR versions expose different APIs. This probe records what
    works instead of pretending a fixed API exists.
    """
    image_path = case_dir / "_probe_input_rembg.png"
    _write_temp_image(image, image_path)

    code = f"""
from pathlib import Path
import json
p = Path(r'{str(image_path)}')
result = {{}}
try:
    import paddleocr
    result['paddleocr_import'] = True
    result['paddleocr_version'] = getattr(paddleocr, '__version__', 'unknown')
    result['symbols'] = [name for name in dir(paddleocr) if 'OCR' in name or 'Class' in name or 'Doc' in name or 'Layout' in name][:100]
    try:
        from paddleocr import PaddleOCR
        result['PaddleOCR_available'] = True
        # Try both old and new argument names conservatively.
        attempts = []
        for kwargs in [
            {{'use_angle_cls': True, 'lang': 'en', 'show_log': False}},
            {{'use_angle_cls': True, 'lang': 'en'}},
        ]:
            try:
                ocr = PaddleOCR(**kwargs)
                out = ocr.ocr(str(p), cls=True)
                attempts.append({{'kwargs': kwargs, 'ok': True, 'type': str(type(out)), 'excerpt': str(out)[:1200]}})
                break
            except Exception as exc:
                attempts.append({{'kwargs': kwargs, 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)[:500]}})
        result['PaddleOCR_attempts'] = attempts
    except Exception as exc:
        result['PaddleOCR_available'] = False
        result['PaddleOCR_error'] = type(exc).__name__ + ': ' + str(exc)[:500]
except Exception as exc:
    result['paddleocr_import'] = False
    result['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
print(json.dumps(result, ensure_ascii=False))
"""
    proc = _run_py_probe(code, timeout=180)
    manifest["paddleocr_orientation_probe"] = proc

    # This probe is not an image transformer yet; keep input as visual reference.
    _save(image, case_dir / "10_paddleocr_probe_input_reference.png")


def _probe_paddlex_doc_tools(image: Image.Image, case_dir: Path, manifest: dict[str, Any]) -> None:
    image_path = case_dir / "_probe_input_rembg.png"
    _write_temp_image(image, image_path)

    code = """
import json
result = {}
try:
    import paddlex
    result['paddlex_import'] = True
    result['paddlex_version'] = getattr(paddlex, '__version__', 'unknown')
    result['top_symbols'] = [name for name in dir(paddlex) if 'Doc' in name or 'doc' in name or 'OCR' in name or 'ocr' in name or 'Pipeline' in name or 'pipeline' in name][:200]
    try:
        from paddlex import create_pipeline
        result['create_pipeline_available'] = True
        candidate_names = [
            'document_image_orientation_classification',
            'doc_img_orientation_classification',
            'PP-DocLayout',
            'OCR',
        ]
        attempts = []
        for name in candidate_names:
            try:
                pipe = create_pipeline(pipeline=name)
                attempts.append({'pipeline': name, 'ok': True, 'type': str(type(pipe))})
                break
            except Exception as exc:
                attempts.append({'pipeline': name, 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)[:500]})
        result['pipeline_attempts'] = attempts
    except Exception as exc:
        result['create_pipeline_available'] = False
        result['create_pipeline_error'] = type(exc).__name__ + ': ' + str(exc)[:500]
except Exception as exc:
    result['paddlex_import'] = False
    result['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
print(json.dumps(result, ensure_ascii=False))
"""
    manifest["paddlex_doc_probe"] = _run_py_probe(code, timeout=180)
    _save(image, case_dir / "20_paddlex_probe_input_reference.png")


def _probe_doctr_unwarp(image: Image.Image, case_dir: Path, manifest: dict[str, Any]) -> None:
    image_path = case_dir / "_probe_input_rembg.png"
    _write_temp_image(image, image_path)

    code = f"""
import json
result = {{}}
try:
    import doctr
    result['doctr_import'] = True
    result['doctr_version'] = getattr(doctr, '__version__', 'unknown')
    result['symbols'] = [name for name in dir(doctr) if 'io' in name.lower() or 'model' in name.lower() or 'doc' in name.lower()][:100]
    try:
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor
        result['DocumentFile_available'] = True
        result['ocr_predictor_available'] = True
        doc = DocumentFile.from_images(r'{str(image_path)}')
        predictor = ocr_predictor(pretrained=True)
        out = predictor(doc)
        result['ocr_predictor_attempt'] = {{'ok': True, 'type': str(type(out)), 'excerpt': str(out)[:1000]}}
    except Exception as exc:
        result['doctr_attempt_error'] = type(exc).__name__ + ': ' + str(exc)[:700]
except Exception as exc:
    result['doctr_import'] = False
    result['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
print(json.dumps(result, ensure_ascii=False))
"""
    manifest["doctr_probe"] = _run_py_probe(code, timeout=240)
    _save(image, case_dir / "30_doctr_probe_input_reference.png")


def _select_current_best(image: Image.Image, case_dir: Path, manifest: dict[str, Any]) -> None:
    # No proven transform integrated yet. The accepted visual baseline remains rembg-only.
    _save(image, case_dir / "90_current_best_rembg_only.png")
    _save(ImageOps.grayscale(image), case_dir / "91_current_best_rembg_only_grayscale.png")
    manifest["current_best"] = {
        "route": "rembg_only",
        "reason": "R9-26B is a proven-tool availability probe; no runtime geometry chosen until a real tool route produces better visual output.",
    }


def export_probe(input_path: Path, member: str | None, out_dir: Path) -> Path:
    data, filename = _load_bytes(input_path, member)
    case_dir = out_dir / _safe_stem(filename)
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_started": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_path),
        "member": member or filename,
        "goal": "R9-26B: probe real/proven document tools only; no custom geometry integration.",
        "module_inventory": _module_inventory(),
    }

    rembg_img = _rembg_neutralized(data, manifest)
    _save(rembg_img, case_dir / "01_rembg_neutralized.png")

    _probe_paddleocr_orientation(rembg_img, case_dir, manifest)
    _probe_paddlex_doc_tools(rembg_img, case_dir, manifest)
    _probe_doctr_unwarp(rembg_img, case_dir, manifest)
    _select_current_best(rembg_img, case_dir, manifest)

    for tmp in case_dir.glob("_probe_input_*"):
        try:
            tmp.unlink()
        except Exception:
            pass

    manifest["files"] = sorted(p.name for p in case_dir.iterdir())
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (case_dir / "manifest.txt").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return case_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="R9-26B probe real document/OCR geometry tools after rembg.")
    parser.add_argument("input")
    parser.add_argument("--member", default=None)
    parser.add_argument("--out", default="/tmp/R9-26B_real_document_tools_probe")
    args = parser.parse_args()

    out = export_probe(Path(args.input), args.member, Path(args.out))
    print(f"R9-26B real document tools probe geschreven naar: {out}")
    for item in sorted(out.iterdir()):
        print(f"{item.name}\t{item.stat().st_size} bytes")


if __name__ == "__main__":
    main()
