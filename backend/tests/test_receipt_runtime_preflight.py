import pytest

from app import runtime_preflight


def test_runtime_preflight_warms_image_and_primary_ocr_before_health(monkeypatch):
    calls = []

    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_image_preprocessing',
        lambda: calls.append('image') or {'status': 'ok', 'warmup': 'receipt_image_preprocessing'},
    )
    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_ocr_runtime',
        lambda: calls.append('ocr') or {'paddle_ready': True, 'tesseract_ready': True},
    )
    monkeypatch.setenv('REZZERV_RECEIPT_STARTUP_REMBG_WARMUP', 'true')
    monkeypatch.setenv('REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP', 'true')

    result = runtime_preflight.run_runtime_preflight()

    assert calls == ['image', 'ocr']
    assert result['status'] == 'ok'
    assert result['ocr_runtime']['paddle_ready'] is True


def test_runtime_preflight_fails_closed_when_paddle_is_not_ready(monkeypatch):
    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_image_preprocessing',
        lambda: {'status': 'ok'},
    )
    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_ocr_runtime',
        lambda: {'paddle_ready': False, 'tesseract_ready': True},
    )
    monkeypatch.setenv('REZZERV_RECEIPT_STARTUP_REMBG_WARMUP', 'true')
    monkeypatch.setenv('REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP', 'true')

    with pytest.raises(RuntimeError, match='Paddle OCR warmup failed'):
        runtime_preflight.run_runtime_preflight()


def test_runtime_preflight_keeps_explicit_paddle_diagnostic_escape_hatch(monkeypatch):
    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_image_preprocessing',
        lambda: {'status': 'ok'},
    )
    monkeypatch.setattr(
        runtime_preflight,
        'warm_receipt_ocr_runtime',
        lambda: {'paddle_ready': False, 'tesseract_ready': True},
    )
    monkeypatch.setenv('REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP', 'false')

    result = runtime_preflight.run_runtime_preflight()

    assert result['ocr_runtime'] == {
        'paddle_ready': False,
        'tesseract_ready': True,
    }
