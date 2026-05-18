from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'nginx.conf'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6-cache')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old = """    location = /version.json {
        add_header Cache-Control \"no-cache, no-store, must-revalidate\" always;
        add_header Pragma \"no-cache\" always;
        add_header Expires \"0\" always;
        expires -1;
        try_files $uri =404;
    }

    location /api/ {
"""

new = """    location = /version.json {
        add_header Cache-Control \"no-cache, no-store, must-revalidate\" always;
        add_header Pragma \"no-cache\" always;
        add_header Expires \"0\" always;
        expires -1;
        try_files $uri =404;
    }

    location = /index.html {
        add_header Cache-Control \"no-cache, no-store, must-revalidate\" always;
        add_header Pragma \"no-cache\" always;
        add_header Expires \"0\" always;
        expires -1;
        try_files $uri =404;
    }

    location /assets/ {
        add_header Cache-Control \"public, max-age=31536000, immutable\" always;
        try_files $uri =404;
    }

    location /api/ {
"""

if new not in content:
    if old not in content:
        raise SystemExit('R6-cache patch aborted: version/api anchor not found.')
    content = content.replace(old, new, 1)

old_root = """    location / {
        try_files $uri /index.html;
    }
"""
new_root = """    location / {
        add_header Cache-Control \"no-cache, no-store, must-revalidate\" always;
        add_header Pragma \"no-cache\" always;
        add_header Expires \"0\" always;
        expires -1;
        try_files $uri /index.html;
    }
"""

if new_root not in content:
    if old_root not in content:
        raise SystemExit('R6-cache patch aborted: root location anchor not found.')
    content = content.replace(old_root, new_root, 1)

required = [
    'location = /index.html',
    'location /assets/',
    'no-cache, no-store, must-revalidate',
    'public, max-age=31536000, immutable',
]
for marker in required:
    if marker not in content:
        raise SystemExit(f'R6-cache guard failed: {marker!r} missing.')

TARGET.write_text(content, encoding='utf-8')
print('R6-cache frontend headers patch applied to', TARGET)
print('Backup written to', BACKUP)
