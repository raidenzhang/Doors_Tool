"""Import Excel worksheets as groups of editable requirement rows."""

from bisect import bisect_right
from datetime import date, time
from pathlib import Path
import re

from openpyxl import load_workbook

from requirement_structure import table_row_metadata, table_row_text


def cell_text(cell, cached_sheet):
    value = cell.value
    if cell.data_type == 'f':
        cached = cached_sheet[cell.coordinate].value
        value = cached if cached is not None else getattr(value, 'text', value)
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, int) and value >= 0 and re.fullmatch(r'0+', cell.number_format):
        return str(value).zfill(len(cell.number_format))
    return str(value)


def sheet_rows(sheet, cached):
    rows = {}
    for number, cells in enumerate(sheet.iter_rows(), 1):
        values = [cell_text(cell, cached) for cell in cells]
        while values and not values[-1].strip():
            values.pop()
        if values:
            rows[number] = values

    # Carry vertically merged identifiers into populated data rows so each
    # exported signal or service row retains its message or service context.
    copy_merged_values(rows, ((area.min_row, area.max_row, area.min_col - 1)
                              for area in sheet.merged_cells.ranges))
    return rows


def copy_merged_values(rows, ranges):
    numbers = sorted(rows)
    for first_row, last_row, column in ranges:
        if first_row == last_row or first_row not in rows:
            continue
        first = rows[first_row]
        if column >= len(first) or not first[column].strip():
            continue
        for number in numbers[bisect_right(numbers, first_row):bisect_right(numbers, last_row)]:
            row = rows[number]
            if len(row) <= column:
                row.extend([''] * (column + 1 - len(row)))
            row[column] = first[column]


def worksheet_items(path, name, rows):
    if not rows:
        return []
    first, last = min(rows), max(rows)
    metadata = table_row_metadata([rows.get(number, []) for number in range(first, last + 1)])
    source = f'{Path(path).name}:{name}'
    return [
        dict(text=name, level=0, page=source, uncertain=False),
        *(dict(text=table_row_text(row['cells']), level=1,
               page=f'{source}:行 {first + offset}', uncertain=True, table_row=row)
          for offset, row in metadata.items()),
    ]


def parse_legacy_excel(path):
    import xlrd

    book = xlrd.open_workbook(str(path), formatting_info=True, ragged_rows=True)
    try:
        items = []
        for sheet in book.sheets():
            rows = {}
            for index in range(sheet.nrows):
                values = []
                for cell in sheet.row(index):
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        value = xlrd.xldate_as_datetime(value, book.datemode).isoformat()
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value = 'TRUE' if value else 'FALSE'
                    elif cell.ctype == xlrd.XL_CELL_ERROR:
                        value = xlrd.error_text_from_code.get(value, '#ERROR!')
                    elif cell.ctype == xlrd.XL_CELL_NUMBER and float(value).is_integer():
                        value = int(value)
                        if cell.xf_index is not None:
                            fmt = book.format_map.get(book.xf_list[cell.xf_index].format_key)
                            if value >= 0 and fmt and re.fullmatch(r'0+', fmt.format_str):
                                value = str(value).zfill(len(fmt.format_str))
                    values.append(str(value))
                while values and not values[-1].strip():
                    values.pop()
                if values:
                    rows[index + 1] = values
            copy_merged_values(rows, ((first + 1, end, column)
                                      for first, end, column, _ in sheet.merged_cells))
            items.extend(worksheet_items(path, sheet.name, rows))
        return items
    finally:
        book.release_resources()


def parse_excel(path):
    if Path(path).suffix.lower() == '.xls':
        return parse_legacy_excel(path)
    workbook = load_workbook(path, keep_links=False)
    try:
        cached = load_workbook(path, data_only=True, keep_links=False)
        try:
            items = []
            for sheet in workbook.worksheets:
                rows = sheet_rows(sheet, cached[sheet.title])
                items.extend(worksheet_items(path, sheet.title, rows))
            return items
        finally:
            cached.close()
    finally:
        workbook.close()
