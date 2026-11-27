from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from dxl_export import generate
from excel_parser import parse_excel


class ExcelTests(unittest.TestCase):
    def test_com_matrix_and_uds_preserve_context_and_source_rows(self):
        workbook = Workbook()
        matrix = workbook.active
        matrix.title = 'Com Matrix'
        matrix.append(['CAN ID', 'Signal', 'Length'])
        matrix.append(['0x01A', '速度', 16])
        matrix.append([None, 'Status', 8])
        matrix.merge_cells('A2:A3')
        matrix['B5'] = 'Checksum'
        matrix['C5'] = '=4+4'
        uds = workbook.create_sheet('UDS')
        uds.append(['SID', 'Service'])
        uds.append([10, 'DiagnosticSessionControl'])
        uds['A2'].number_format = '000'
        workbook.create_sheet('Empty')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'vehicle.xlsx'
            workbook.save(path)
            items = parse_excel(path)
        self.assertEqual([item['text'] for item in items], [
            'Com Matrix', 'CAN ID Signal Length', '0x01A 速度 16', '0x01A Status 8',
            'Checksum =4+4', 'UDS', 'SID Service', '010 DiagnosticSessionControl',
        ])
        self.assertEqual([item['level'] for item in items], [0, 1, 1, 1, 1, 0, 1, 1])
        self.assertEqual(items[4]['page'], 'vehicle.xlsx:Com Matrix:行 5')
        self.assertEqual(items[4]['table_row']['cells'], ['', 'Checksum', '=4+4'])
        self.assertEqual(items[4]['table_row']['before'], 1)
        self.assertIn('= table(below(obj0), 5, 3)', generate(items, native_tables=True))
