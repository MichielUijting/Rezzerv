from __future__ import annotations

from pathlib import Path

path = Path("frontend/src/features/receipts/KassaPage.jsx")
text = path.read_text(encoding="utf-8")

old = """            {emailRouteError && ['admin','owner'].includes(String(currentUserDisplayRole || '').trim().toLowerCase()) && (technicalUploadError?.detail || String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.')) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""
new = """            {['admin','owner'].includes(String(currentUserDisplayRole || '').trim().toLowerCase()) && (technicalUploadError?.detail || (emailRouteError && String(emailRouteError || '').startsWith('Upload mislukt. De server gaf een technische fout terug.'))) ? (
              <div style={{ display: 'grid', gap: '8px' }}>
"""

if old not in text:
    raise SystemExit("Technische-foutknop conditie niet gevonden; patch niet uitgevoerd.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Admin technische foutmelding zichtbaar gemaakt op basis van technicalUploadError.")
print("De knop verschijnt nu ook wanneer de algemene melding groen is maar er wel een technische uploadfout is vastgelegd.")
