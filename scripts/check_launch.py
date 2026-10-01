"""Fail production Netlify builds until the operator has supplied legal pages."""
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / 'site'
placeholders = (
    'RECHTLICHE_ANGABEN_FEHLEN', 'Betreiberangaben vor Veröffentlichung ergänzen',
    '[Vor- und Nachname', '[ladungsfähige Anschrift]', '[E-Mail-Adresse]',
    '[zuständige Datenschutz-Aufsichtsbehörde',
)
for filename in ('impressum.html', 'datenschutz.html'):
    file = SITE / filename
    if not file.exists():
        raise SystemExit(f'{file}: Seite fehlt; Veröffentlichung gestoppt. Siehe README.md.')
    text = file.read_text(encoding='utf-8')
    remaining = [marker for marker in placeholders if marker in text]
    if remaining:
        raise SystemExit(f'{file}: Platzhalter {remaining[0]!r} noch vorhanden; Veröffentlichung gestoppt. Siehe README.md.')
print('Rechtliche Seiten vorhanden; inhaltliche Richtigkeit liegt beim Betreiber.')
