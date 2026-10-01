import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
import unittest

import pymupdf

from scripts.pdf_menu import LayoutError, clean_text, parse_pdf
from scripts.update import HOME, PRIMARY, pdf_links, update


def sample_pdf(weeks=8, broken=None, missing_header=False):
    document = pymupdf.open()
    monday = date(2026, 8, 10)
    for week in range(weeks):
        page = document.new_page(width=842, height=595)
        page.insert_text((2, 75), "Menü I", fontsize=9)
        page.insert_text((2, 167), "Menü II", fontsize=9)
        page.insert_text((2, 262), "Dessert", fontsize=9)
        for col in range(5):
            number = week * 5 + col
            day = monday + timedelta(days=7 * week + col)
            x = 68 + 154 * col
            if not (missing_header and col == 4):
                page.insert_text((x + 23, 62), day.strftime("%d.%m.%Y"), fontsize=9)
            page.insert_text((x, 90), f"Nudeln {number} mit Sauce (a1)", fontsize=9)
            page.insert_text((x, 192),
                             "Kartoffeln (a1" if number == broken else "siehe Menü I", fontsize=9)
            page.insert_text((x, 266), f"Apfel {number}", fontsize=9)
    result = document.tobytes()
    document.close()
    return result


class ParserTests(unittest.TestCase):
    def test_full_eight_week_document_and_weekday_mapping(self):
        result = parse_pdf(sample_pdf())
        self.assertEqual((result['start'], result['end'], result['pages']),
                         ('2026-08-10', '2026-10-02', 8))
        self.assertEqual(len(result['days']), 40)
        for day, value in result['days'].items():
            self.assertEqual(value['status'], 'ok', day)
            self.assertEqual(value['menu_i'], value['menu_ii'])
            self.assertTrue(value['menu_ii_from_i'])
        self.assertEqual(result['days']['2026-09-29']['menu_i'], 'Nudeln 36 mit Sauce (a1)')

    def test_uncertain_day_does_not_hide_neighbours(self):
        result = parse_pdf(sample_pdf(weeks=1, broken=2))['days']
        self.assertEqual(result['2026-08-12']['status'], 'uncertain')
        self.assertEqual(sum(v['status'] == 'ok' for v in result.values()), 4)

    def test_unknown_layout_rejected(self):
        with self.assertRaises(LayoutError):
            parse_pdf(sample_pdf(weeks=1, missing_header=True))
        with self.assertRaises(LayoutError):
            parse_pdf(b'not a PDF')

    def test_vegetarian_reference_to_fish_is_blocked(self):
        document = pymupdf.open()
        page = document.new_page(width=842, height=595)
        page.insert_text((2, 75), 'Menü I', fontsize=9)
        page.insert_text((2, 167), 'Menü II', fontsize=9)
        page.insert_text((2, 262), 'Dessert', fontsize=9)
        for col in range(5):
            x = 68 + 154 * col
            page.insert_text((x + 23, 62), (date(2026, 8, 10) + timedelta(days=col)).strftime('%d.%m.%Y'), fontsize=9)
            page.insert_text((x, 90), 'Fisch (F)' if col == 0 else 'Reis', fontsize=9)
            page.insert_text((x, 192), 'siehe Menü I', fontsize=9)
            page.insert_text((x, 266), 'Apfel', fontsize=9)
        result = parse_pdf(document.tobytes())
        document.close()
        self.assertEqual(result['days']['2026-08-10']['status'], 'uncertain')
        self.assertEqual(result['days']['2026-08-11']['status'], 'ok')

    def test_only_line_end_hyphen_joined(self):
        self.assertEqual(clean_text(['Roggen- und Dinkelbrot', 'mit Salat']),
                         'Roggen- und Dinkelbrot mit Salat')
        self.assertEqual(clean_text(['Tomaten-', 'Suppe']), 'Tomaten-Suppe')


class DiscoveryTests(unittest.TestCase):
    def test_scrapling_links_same_site_only(self):
        html = b'<a href="/plan.pdf">Speiseplan</a><a href="https://bad.example/evil.pdf">Speiseplan</a><a href="/bericht.pdf">Bericht</a>'
        links = pdf_links(html, HOME + '/organisation/')
        self.assertEqual([link.url for link in links], [HOME + '/plan.pdf'])

    def test_link_moved_to_another_school_page(self):
        page = HOME + '/organisation/'
        url = HOME + '/wp-content/uploads/2026/08/Speiseplan.pdf'
        inputs = {PRIMARY: b'<p>Der Speiseplan ist umgezogen.</p>',
                  page: f'<p>Aktueller <a href="{url}">Speiseplan</a></p>'.encode(),
                  url: sample_pdf()}
        result, _ = update(date(2026, 9, 29), get=lambda u: inputs[u], pages=lambda: [page])
        self.assertIn('2026-09-29', result['days'])
        self.assertEqual(result['days']['2026-09-29']['status'], 'ok')

    def test_source_changed_but_parser_failed_blocks_old_days(self):
        url = HOME + '/plan.pdf'
        old = {'sources': {url: {'url': url, 'start': '2026-08-10', 'end': '2026-10-02',
                                 'sha256': hashlib.sha256(b'%PDF-previous').hexdigest()}},
               'days': {'2026-09-29': {'status': 'ok', 'menu_i': 'Alt', 'source': url}}}
        html = f'<a href="{url}">Speiseplan</a>'.encode()
        inputs = {PRIMARY: html, url: b'%PDF-new-and-corrupted'}
        result, warnings = update(date(2026, 9, 29), old, get=lambda u: inputs[u], pages=lambda: [])
        self.assertEqual(result['days']['2026-09-29']['status'], 'uncertain')
        self.assertTrue(any('Import fehlgeschlagen' in warning for warning in warnings))

    def test_older_unlabelled_pdf_not_preferred(self):
        good = HOME + '/wp-content/uploads/2026/08/Speiseplan.pdf'
        page = f'<a href="{HOME}/wp-content/uploads/2024/11/47.2024.pdf">–</a><a href="{good}">Speiseplan 2026</a>'.encode()
        # The older candidate is rejected before parsing by its old date.
        older = pymupdf.open()
        oldpage = older.new_page()
        oldpage.insert_text((30, 30), '18.11.2024')
        old_bytes = older.tobytes()
        older.close()
        inputs = {PRIMARY: page, good: sample_pdf(), HOME + '/wp-content/uploads/2024/11/47.2024.pdf': old_bytes}
        result, warnings = update(date(2026, 9, 29), get=lambda u: inputs[u], pages=lambda: [])
        self.assertEqual(len(result['days']), 40)
        self.assertEqual(set(result['sources']), {good})
        self.assertEqual(warnings, ['Kein Folgeplan gefunden; vorhandener Plan endet am 2026-10-02'])

    def test_expired_plan_is_not_kept_as_an_archive(self):
        url = HOME + '/Speiseplan.pdf'
        inputs = {PRIMARY: f'<a href="{url}">Speiseplan</a>'.encode(), url: sample_pdf()}
        result, warnings = update(date(2026, 10, 3), get=lambda u: inputs[u], pages=lambda: [])
        self.assertEqual(result['days'], {})
        self.assertEqual(result['sources'], {})
        self.assertEqual(result['fallback_pdf']['url'], url)
        self.assertIn('Kein aktueller Speiseplan gefunden', warnings)

    def test_published_json_shape(self):
        snapshot = json.loads((Path(__file__).resolve().parents[1] / 'site/data/menu.json').read_text())
        self.assertEqual(snapshot['schema'], 1)
        for day, entry in snapshot['days'].items():
            self.assertEqual(date.fromisoformat(day).isoformat(), day)
            self.assertIn(entry['source'], snapshot['sources'])
            self.assertIn(entry['status'], ('ok', 'uncertain'))
            if entry['status'] == 'ok':
                for key in ('menu_i', 'menu_ii', 'dessert'):
                    self.assertTrue(entry[key], (day, key))


if __name__ == '__main__':
    unittest.main()
