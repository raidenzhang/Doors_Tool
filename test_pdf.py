from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import fitz

from dxl_export import generate, write_image_bundle
from pdf_parser import parse_files


class PdfParserTests(unittest.TestCase):
    def test_extracts_pdf_bitmap_and_packages_it_for_the_preceding_requirement(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            bundle = Path(directory) / 'sample.zip'
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((50, 100), 'REQ-1 See the braking diagram below.')
                picture = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False)
                picture.clear_with(100)
                page.insert_image(fitz.Rect(50, 125, 130, 185), pixmap=picture)
                page.insert_text((50, 225), 'REQ-2 Record the warning.')
                document.save(path)
            items = parse_files([path], 5, 12)
            self.assertEqual(len(items), 2)
            self.assertEqual(len(items[0]['images']), 1)
            self.assertNotIn('images', items[1])
            self.assertEqual(write_image_bundle(bundle, items), 1)
            with ZipFile(bundle) as archive:
                self.assertIn('embedBundleImage(obj0,', archive.read('import.dxl').decode('ascii'))
                image_name = next(name for name in archive.namelist() if name.startswith('images/'))
                self.assertTrue(archive.read(image_name).startswith(b'\x89PNG'))
                original = archive.read(image_name)
            items[0]['images'].append((None, original))
            self.assertEqual(write_image_bundle(bundle, items), 2)
            with ZipFile(bundle) as archive:
                script = archive.read('import.dxl').decode('ascii')
                self.assertEqual(script.count('embedBundleImage(obj0,'), 1)
                images = [archive.read(name) for name in archive.namelist() if name.startswith('images/')]
                combined = next(data for data in images if data != original)
                self.assertEqual(fitz.Pixmap(combined).height, 2 * fitz.Pixmap(original).height)

    def test_keeps_markers_when_pdf_stores_them_as_separate_text(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            with fitz.open() as document:
                page = document.new_page()
                for y, marker, text in [(90, '(1)', 'First action.'), (113, '(2)', 'Second action.'),
                                        (137, 'a)', 'Check result.')]:
                    page.insert_text((50, y), marker)
                    page.insert_text((83, y), text)
                document.save(path)
            items = parse_files([path], 5, 12)
        self.assertEqual([item['text'] for item in items],
                         ['(1) First action.', '(2) Second action.', 'a) Check result.'])

    def test_wrapping_row_fragments_and_repeated_margins(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            with fitz.open() as document:
                for number in (1, 2):
                    page = document.new_page()
                    page.insert_text((50, 29), 'System specification')
                    page.insert_text((50, 120), f'1.{number}')
                    page.insert_text((78, 120), f'Function {number} .............')
                    page.insert_text((210, 120), str(number + 9))
                    page.insert_text(
                        (50, 152),
                        'REQ-1 The system shall maintain an active\nwarning until the signal clears.',
                    )
                    page.insert_text((50, 181), 'REQ-2 The system shall log the warning.')
                    page.insert_text((50, 807), f'Internal use - Page {number} of 2')
                    page.insert_text((530, 807), str(number))
                document.save(path)

            items = parse_files([path], gap=5, indent=12)

        self.assertEqual([item['text'] for item in items], [
            'REQ-1 The system shall maintain an active\nwarning until the signal clears.',
            'REQ-2 The system shall log the warning.',
            'REQ-1 The system shall maintain an active\nwarning until the signal clears.',
            'REQ-2 The system shall log the warning.',
        ])
        self.assertEqual([item['page'] for item in items], ['sample.pdf:1'] * 2 + ['sample.pdf:2'] * 2)

    def test_pdf_front_matter_outline_tables_captions_and_subrequirements(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            with fitz.open() as document:
                front = document.new_page()
                front.insert_text((50, 100), 'Cover Page')
                front.insert_text((50, 136), 'Introduction')
                front.insert_text((50, 155), 'A non-requirement introduction.')
                front.insert_text((50, 190), 'Table of Contents')
                front.insert_text((50, 210), '1')
                front.insert_text((50, 230), 'General Functions ........ 2')
                front.insert_text((50, 250), '1.1 Braking ........ 2')
                page = document.new_page()
                page.insert_text((50, 100), 'General Functions', fontname='hebo', fontsize=15)
                page.insert_text((50, 130), 'Braking')
                page.insert_text((50, 160), 'Performance requirements are as follows:')
                for x in (50, 170, 290, 410):
                    page.draw_line((x, 185), (x, 235))
                for y in (185, 210, 235):
                    page.draw_line((50, y), (410, y))
                for x, y, value in [(56, 201, 'Parameter'), (176, 201, 'Limit'),
                                    (296, 201, 'Notes'), (56, 226, 'Response'), (176, 226, '250 ms')]:
                    page.insert_text((x, y), value)
                page.insert_text((50, 255), 'Table 8: Response limits')
                page.insert_text((50, 280), 'Figure 1')
                page.insert_text((50, 305), 'Test cases:')
                page.insert_text((50, 324), '1. The controller shall monitor the signal and')
                page.insert_text((50, 346), 'store the warning for')
                page.insert_text((50, 366), 'later review.')
                page.insert_text((50, 389), '2. Clear the warning.')
                page.insert_text((50, 415), 'The controller shall log errors in Table 8.')
                document.set_toc([[1, 'General Functions', 2], [2, 'Braking', 2]])
                document.save(path)
            items = parse_files([path], gap=5, indent=12)

        self.assertEqual([item['text'] for item in items], [
            'General Functions', 'Braking', 'Performance requirements are as follows:',
            'Parameter Limit Notes', 'Response 250 ms', 'Test cases:',
            '1. The controller shall monitor the signal and\nstore the warning for\nlater review.',
            '2. Clear the warning.', 'The controller shall log errors in Table 8.',
        ])
        self.assertEqual([item['level'] for item in items], [0, 1, 2, 3, 3, 2, 3, 3, 2])
        self.assertEqual({item['page'] for item in items}, {'sample.pdf:2'})
        self.assertEqual(items[3]['table_row']['cells'], ['Parameter', 'Limit', 'Notes'])
        self.assertEqual(items[4]['table_row']['cells'], ['Response', '250 ms', ''])
        self.assertEqual(items[3]['table_row']['id'], items[4]['table_row']['id'])
        script = generate(items, native_tables=True)
        self.assertIn('Object obj3 = table(below(obj2), 2, 3)', script)
        self.assertIn('pos3 == 4) { cell3."Object Text" = "250 ms"', script)
        self.assertNotIn('pos3 == 5', script)

    def test_hanging_indent_with_overlapping_line_boxes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((50, 100), '1) Check the input signal and report')
                page.insert_text((68, 111), 'an error if it is invalid')
                page.insert_text((50, 122), '2) Store the result.')
                document.save(path)

            items = parse_files([path], gap=5, indent=12)

        self.assertEqual([item['text'] for item in items], [
            '1) Check the input signal and report\nan error if it is invalid',
            '2) Store the result.',
        ])


if __name__ == '__main__':
    unittest.main()
