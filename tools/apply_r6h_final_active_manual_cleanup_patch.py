from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SERVICE = ROOT / 'backend' / 'app' / 'services' / 'receipt_status_baseline_service.py'
REVIEW_PAGE = ROOT / 'frontend' / 'src' / 'pages' / 'ReceiptReviewPreviewPage.jsx'

for target in [BASELINE_SERVICE, REVIEW_PAGE]:
    content = target.read_text(encoding='utf-8-sig')
    target.with_suffix(target.suffix + '.bak-r6h').write_text(content, encoding='utf-8')

baseline = BASELINE_SERVICE.read_text(encoding='utf-8-sig')
baseline = baseline.replace(
    "STATUS_LABELS = {\n    'approved': 'Gecontroleerd',\n    'review_needed': 'Controle nodig',\n    'manual': 'Handmatig',\n}\n",
    "STATUS_LABELS = {\n    'approved': 'Gecontroleerd',\n    'review_needed': 'Controle nodig',\n}\n",
)
baseline = baseline.replace('manual: ', 'review_needed: ')
baseline = baseline.replace("expected_status == 'manual'", "expected_status == 'review_needed'")
baseline = baseline.replace("actual_status == 'manual'", "actual_status == 'review_needed'")
baseline = baseline.replace('Edge-case 1: een handmatige bon zonder totaal in zowel baseline als actuele set', 'Edge-case 1: een review-bon zonder totaal in zowel baseline als actuele set')
BASELINE_SERVICE.write_text(baseline, encoding='utf-8')

review = REVIEW_PAGE.read_text(encoding='utf-8-sig')
replacements = {
    "key: 'manual_entry'": "key: 'review_input'",
    "title: 'Handmatig invoeren'": "title: 'Correctie nodig'",
    "Er is te weinig bruikbare informatie om deze bon via OCR te beoordelen.": "Er is te weinig bruikbare informatie; corrigeer deze bon in de reviewflow.",
    "readiness === 'manual_entry_needed'": "readiness === 'review_input_needed'",
    "action === 'manual_entry'": "action === 'correct_in_review'",
    "return 'Voer deze bon handmatig in'": "return 'Corrigeer deze bon in de reviewflow'",
    "return 'manual_entry'": "return 'review_input'",
    "return 'Er is te weinig betrouwbare OCR-informatie.'": "return 'Er is te weinig betrouwbare OCR-informatie; reviewcorrectie is nodig.'",
    "return 'manual_entry'": "return 'review_input'",
    "Controleer deze bon handmatig voordat verwerking wordt overwogen.": "Controleer deze bon in de reviewflow voordat verwerking wordt overwogen.",
}
for old, new in replacements.items():
    review = review.replace(old, new)
review = review.replace('manual_entry_needed', 'review_input_needed')
review = review.replace('manual_entry', 'correct_in_review')
review = review.replace('Handmatig invoeren', 'Correctie nodig')
REVIEW_PAGE.write_text(review, encoding='utf-8')

# Guard active legacy markers in scoped files. Ordinary Dutch lowercase handmatig outside these flows is out of scope.
checks = {
    BASELINE_SERVICE: ["'manual': 'Handmatig'", 'manual:', "expected_status == 'manual'", "actual_status == 'manual'"],
    REVIEW_PAGE: ['manual_entry_needed', 'manual_entry', 'Handmatig invoeren'],
}
for path, markers in checks.items():
    text = path.read_text(encoding='utf-8')
    for marker in markers:
        if marker in text:
            raise SystemExit(f'R6h guard failed: {marker!r} still present in {path}')

print('R6h final active manual cleanup patch applied')
print('Updated:', BASELINE_SERVICE)
print('Updated:', REVIEW_PAGE)
