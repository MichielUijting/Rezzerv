$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33G apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py')
text = path.read_text(encoding='utf-8')
start = text.index('def _order_quad_points(points: Any) -> Any:')
end = text.index('\n\ndef _perspective_normalize_from_dark_receipt_region', start)
replacement = '''def _order_quad_points(points: Any) -> Any:\n    pts = np.array(points, dtype="float32").reshape(4, 2)\n    center = pts.mean(axis=0)\n    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])\n    ring = pts[np.argsort(angles)]\n\n    edges = []\n    for index in range(4):\n        first = ring[index]\n        second = ring[(index + 1) % 4]\n        edges.append((float((first[1] + second[1]) / 2.0), index, first, second))\n    _, top_index, top_a, top_b = min(edges, key=lambda item: item[0])\n\n    if top_a[0] <= top_b[0]:\n        tl, tr = top_a, top_b\n    else:\n        tl, tr = top_b, top_a\n\n    bottom_a = ring[(top_index + 2) % 4]\n    bottom_b = ring[(top_index + 3) % 4]\n    if bottom_a[0] <= bottom_b[0]:\n        bl, br = bottom_a, bottom_b\n    else:\n        bl, br = bottom_b, bottom_a\n\n    return np.array([tl, tr, br, bl], dtype="float32")\n'''
text = text[:start] + replacement + text[end:]
compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('R9-33G applied: robust quad ordering')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-33G failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py
git add backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py
git commit -m 'R9-33G fix receipt quad ordering'
git push
Write-Host 'R9-33G toegepast en gepusht.'
