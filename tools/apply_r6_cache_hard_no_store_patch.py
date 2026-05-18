from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'nginx.conf'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6-cache-hard')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old_assets = '''    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files $uri =404;
    }
'''

new_assets = '''    location /assets/ {
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
        expires -1;
        try_files $uri =404;
    }
'''

if old_assets not in content and new_assets not in content:
    raise SystemExit('R6-cache-hard patch aborted: /assets/ cache block not found.')
if old_assets in content:
    content = content.replace(old_assets, new_assets, 1)

# Keep root/index/version explicitly no-store. The duplicate no-cache from nginx expires is harmless,
# but the key guarantee is that neither index.html nor JS/CSS assets can remain stale.
required = [
    'location = /index.html',
    'location /assets/',
    'no-store, no-cache, must-revalidate',
]
for marker in required:
    if marker not in content:
        raise SystemExit(f'R6-cache-hard guard failed: {marker!r} missing.')

TARGET.write_text(content, encoding='utf-8')
print('R6-cache-hard patch applied to', TARGET)
print('Backup written to', BACKUP)
