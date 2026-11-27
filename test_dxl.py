import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dxl_export import generate, read_script, write_script

class DxlTests(unittest.TestCase):
    def test_table_image_coordinates_after_blank_rows_and_at_last_column(self):
        cells = [''] * 19 + ['Figure 20']
        rows = [dict(level=0, text='Figure 20', table_row=dict(id='large', cells=cells, before=49, after=0),
                     image_files=[(19, 'images/example.png')])]
        script = generate(rows, native_tables=True, asset_root='')
        self.assertIn('tableRowNumber0 < 50', script)
        self.assertIn('tableColumnNumber0 < 20', script)
        self.assertIn('tableRowNumber0 == 49 && tableColumnNumber0 == 19', script)
        self.assertIn('pos0 == 999 && !oleIsObject(cell0)', script)
        self.assertNotIn('pos0 == 999) { cell0."Object Text"', script)

    def test_native_dxl_preserves_cell_positions_and_reopens(self):
        rows = [
            dict(level=0, text='Requirements:'),
            dict(level=1, text='Parameter Limit Notes',
                 table_row=dict(id='table-a', cells=['Parameter', 'Limit', 'Notes'], before=0, after=0)),
            dict(level=1, text='Speed 60 km/h Maximum',
                 table_row=dict(id='table-a', cells=['Speed', '', '60 km/h\nMaximum'], before=1, after=0)),
            dict(level=1, text='After table'),
        ]
        script = generate(rows, native_tables=True)
        self.assertIn('Object obj1 = table(below(obj0), 3, 3)', script)
        self.assertIn('pos1 == 6', script)
        self.assertNotIn('pos1 == 7', script)
        self.assertIn('pos1 == 8) { cell1."Object Text" = "60 km/h\\nMaximum"', script)
        self.assertIn('Object obj2 = create after obj1', script)
        self.assertNotIn('table(below', generate(rows))
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'native.dxl'
            write_script(path, rows, native_tables=True)
            restored = read_script(path)
        self.assertEqual(restored[2]['table_row'], rows[2]['table_row'])
        self.assertEqual([item['level'] for item in restored], [0, 1, 1, 1])

    def test_read_back_exported_text_and_levels(self):
        rows = [
            dict(level=0, text='1. 制动要求 ≤ 250 ms'),
            dict(level=1, text='1.1 路径 C:\\test\n下一行\t"引号"'),
            dict(level=2, text='1.1.1 第三级\u2028字符'),
            dict(level=1, text='1.2 同级'),
            dict(level=0, text='2. 下一章'),
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'saved.dxl'
            write_script(path, rows)
            restored = read_script(path)
        self.assertEqual([(row['level'], row['text']) for row in restored],
                         [(row['level'], row['text']) for row in rows])
        self.assertEqual(restored[4]['page'], 'saved.dxl:对象 5')

    def test_read_rejects_extra_statements_and_future_references(self):
        script = generate([dict(level=0, text='Root'), dict(level=1, text='Child')])
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'saved.dxl'
            for modified in (script + 'halt\r\n', script.replace('create below obj0', 'create below obj9')):
                with self.subTest(modified=modified):
                    path.write_bytes(modified.encode('utf-8'))
                    with self.assertRaises(ValueError):
                        read_script(path)

    def test_hierarchy_and_escaping(self):
        rows=[dict(level=n,text=t) for n,t in [(0,'父'),(1,'子"项'),(1,'次子'),(0,'第二根')]]
        script=generate(rows)
        self.assertIn('Object obj0 = create m',script)
        self.assertIn('Object obj1 = create below obj0',script)
        self.assertIn('Object obj2 = create after obj1',script)
        self.assertIn('Object obj3 = create after obj0',script)
        self.assertIn('子\\"项',script)
        self.assertIn('Module is not empty',script)
    def test_invalid_level(self):
        with self.assertRaises(ValueError): generate([dict(level=2,text='a')])

    def test_write_utf8_preserves_unicode_and_hierarchy(self):
        rows = [
            dict(level=0, text='制动要求 ≤ 250 ms'),
            dict(level=1, text='次级要求 "A"\n符号：⌀ 🧪'),
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'requirements.dxl'
            write_script(path, rows)
            data = path.read_bytes()
        self.assertEqual(data.decode('utf-8'), generate(rows))
        self.assertTrue(data.startswith(b'// DOORS'))
        self.assertIn('create below obj0', data.decode('utf-8'))

if __name__ == '__main__': unittest.main()
