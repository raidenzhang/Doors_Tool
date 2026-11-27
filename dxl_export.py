from pathlib import Path
from itertools import groupby
from hashlib import sha256
import json
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile


CREATE_OBJECT = re.compile(r'Object obj(\d+) = create (m|below obj(\d+)|after obj(\d+))')
ASSIGN_TEXT = re.compile(r'obj(\d+)\."Object Text" = "((?:[^"\\]|\\[nt"\\])*)"')
ESCAPES = {'n': '\n', 't': '\t', '"': '"', '\\': '\\'}
NATIVE_DATA = '// DOORS Importer table data: '


def quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\r\n','\n').replace('\r','\n').replace('\n', '\\n').replace('\t', '\\t') + '"'

def generate(items, native_tables=False, asset_root=None, text_files=None):
    if not items: raise ValueError('没有可导出的需求')
    lines = ['// DOORS Classic 9.7.2: use an empty test module.', 'Module m = current', 'if (null m) { ack "Open an empty test module first."; halt }', 'Object existing = first m', 'if (!null existing) { ack "Module is not empty. Import stopped."; halt }', 'if (!confirm "Create objects in this empty test module?" ) { halt }']
    units = []
    for _, group in groupby(items, key=lambda item: (
        item['table_row']['id'], item['level']
    ) if native_tables and 'table_row' in item else None):
        entries = list(group)
        if not native_tables or 'table_row' not in entries[0]:
            units.extend(entries)
            continue
        grid = [dict(entry['table_row'], image_files=entry.get('image_files', ())) for entry in entries]
        units.append(dict(level=entries[0]['level'], grid=grid))
    if asset_root is not None:
        lines.insert(0, f'string assetRoot = {quote(asset_root)}')
        lines.append('int imageFailures = 0')
        files = {name for item in items for _, name in item.get('image_files', ())}
        files.update((text_files or {}).values())
        lines.extend(bundle_folder_check(sorted(files)))
        lines.extend([
            'void embedBundleImage(Object target, string fileName, string location) {',
            'noError()',
            'bool inserted = oleInsert(target, fileName, false)',
            'string details = lastError()',
            'if (!inserted || !null details) {',
            'imageFailures++',
            'print "Cannot embed " fileName " at " location "\\n"',
            'if (!null details) print details "\\n"',
            '}',
            '}',
        ])
    if native_tables:
        for item in items:
            data = {key: item[key] for key in ('level', 'text', 'table_row') if key in item}
            lines.append(NATIVE_DATA + json.dumps(data, separators=(',', ':')))
    previous = []
    deferred_tables = []
    for i, item in enumerate(units):
        level = item['level']
        if not isinstance(level,int) or level < 0 or level > len(previous): raise ValueError(f'第 {i+1} 条层级无效')
        if i == 0:
            if level != 0: raise ValueError('第一条必须为顶层')
            create = 'create m'
        elif level == len(previous): create = f'create below obj{previous[-1]}'
        else: create = f'create after obj{previous[level]}'
        if level == len(previous) and level and 'grid' in units[previous[-1]]:
            raise ValueError('表格行下面还有子需求。请先把子需求移到普通需求下，再导出原生表格。')
        if 'grid' in item:
            if asset_root is not None:
                # Place the table only after all normal objects have been located.
                lines.append(f'Object obj{i} = {create}')
                lines.append(object_check(f'obj{i}', f'Cannot reserve position for table {i + 1}.'))
                deferred_tables.extend(native_table_lines(
                    i, None, item['grid'], True, text_files
                ))
            elif create == 'create m':
                anchor = 'm'
                lines.extend(native_table_lines(i, anchor, item['grid'], False))
            elif create.startswith('create below '):
                anchor = f'below(obj{previous[-1]})'
                lines.extend(native_table_lines(i, anchor, item['grid'], False))
            else:
                anchor = f'obj{previous[level]}'
                lines.extend(native_table_lines(i, anchor, item['grid'], False))
        else:
            lines.append(f'Object obj{i} = {create}')
            if asset_root is not None:
                lines.append(object_check(f'obj{i}', f'Cannot create requirement object {i + 1}.'))
            lines.append(f'obj{i}."Object Text" = {text_expression(item["text"], text_files)}')
            if asset_root is not None:
                lines.extend(embed_image(f'obj{i}', name, f'object {i + 1}') for _, name in item.get('image_files', ()))
        previous = previous[:level] + [i]
    lines.extend(deferred_tables)
    if asset_root is not None:
        lines.append('if (imageFailures > 0) { ack "Some pictures could not be embedded. See DXL output." }')
        lines.append('else { ack "Import complete. Review the objects and save the module." }')
    else:
        lines.append('ack "Import complete. Review the objects and save the module."')
    return '\r\n'.join(lines) + '\r\n'

def asset_expression(name):
    return f'(assetRoot {quote(chr(92) + name.replace("/", chr(92)))})'


def text_expression(text, text_files):
    if text_files and text in text_files:
        return f'readFile({asset_expression(text_files[text])}, 65001)'
    return quote(text)


def object_check(variable, message):
    return f'if (null {variable}) {{ ack {quote(message)}; halt }}'


def bundle_folder_check(files):
    lines = ['string firstMissingFile() {']
    lines.extend(f'if (!canOpenFile({asset_expression(name)}, false)) return {quote(name)}'
                 for name in files)
    lines.extend([
        'return ""',
        '}',
        'DB bundleFolderDialog = null',
        'DBE bundleFolderField = null',
        'bool bundleFolderAccepted = false',
        'void acceptBundleFolder(DB dialog) {',
        'assetRoot = get bundleFolderField',
        'if (assetRoot == "") { ack "Paste the full path to the folder containing import.dxl."; return }',
        'string missing = firstMissingFile()',
        'if (missing != "") { ack ("Import file missing: " missing); return }',
        'bundleFolderAccepted = true',
        'release dialog',
        '}',
        'if (assetRoot == "" || firstMissingFile() != "") {',
        'bundleFolderDialog = create "Locate extracted import folder"',
        'bundleFolderField = field(bundleFolderDialog, "Folder containing import.dxl:", assetRoot, 65)',
        'apply(bundleFolderDialog, "Continue", acceptBundleFolder)',
        'block bundleFolderDialog',
        'destroy bundleFolderDialog',
        'if (!bundleFolderAccepted) halt',
        '}',
    ])
    return lines


def embed_image(target, name, location):
    return f'embedBundleImage({target}, {asset_expression(name)}, {quote(location)})'


def table_conversion_lines(index, row_count, columns, before_conversion=()):
    """Build the header-row-cell hierarchy before converting it to a table."""
    return [
        f'Object tableObj{index} = obj{index}',
        f'Object tableBuildRow{index} = null',
        f'Object tableBuildCell{index} = null',
        f'int tableRowNumber{index}',
        f'int tableColumnNumber{index}',
        f'for (tableRowNumber{index} = 0; tableRowNumber{index} < {row_count}; tableRowNumber{index}++) {{',
        f'if (tableRowNumber{index} == 0) tableBuildRow{index} = create below tableObj{index}',
        f'else tableBuildRow{index} = create after tableBuildRow{index}',
        object_check(f'tableBuildRow{index}', f'Cannot create row for table at object {index + 1}.'),
        f'for (tableColumnNumber{index} = 0; tableColumnNumber{index} < {columns}; tableColumnNumber{index}++) {{',
        f'if (tableColumnNumber{index} == 0) tableBuildCell{index} = create below tableBuildRow{index}',
        f'else tableBuildCell{index} = create after tableBuildCell{index}',
        object_check(f'tableBuildCell{index}', f'Cannot create cell for table at object {index + 1}.'),
        *before_conversion,
        '}',
        '}',
        'noError()',
        f'toTable(tableObj{index})',
        f'string tableConversionError{index} = lastError()',
        f'if (!null tableConversionError{index}) {{ print tableConversionError{index} "\\n"; '
        f'ack "Table conversion failed at object {index + 1} ({row_count} x {columns}). See DXL output."; halt }}',
        f'if (!table(tableObj{index})) {{ ack "Table conversion did not create a table at object {index + 1}."; halt }}',
    ]


def native_table_lines(index, anchor, grid, embed_images, text_files=None):
    for row in grid:
        if (not isinstance(row['id'], str) or not isinstance(row['cells'], list) or not row['cells']
                or any(not isinstance(cell, str) for cell in row['cells'])
                or any(type(row[key]) is not int or row[key] < 0 for key in ('before', 'after'))):
            raise ValueError('表格行数据无效。')
    columns = max(len(row['cells']) for row in grid)
    row_count = sum(1 + row['before'] + row['after'] for row in grid)
    if embed_images:
        variable = f'tableObj{index}'
        before_conversion, checks, pictured_positions = table_cell_pictures(index, grid, columns, text_files)
        lines = table_conversion_lines(index, row_count, columns, before_conversion)
    else:
        variable = f'obj{index}'
        lines = [f'Object {variable} = table({anchor}, {row_count}, {columns})']
        checks, pictured_positions = [], set()
    lines.extend([
        f'Object row{index}',
        f'Object cell{index}',
        f'int pos{index} = 0',
        f'for row{index} in table {variable} do {{',
        f'for cell{index} in row row{index} do {{',
    ])
    if embed_images:
        lines.append(object_check(f'cell{index}', f'Invalid cell in table at object {index + 1}.'))
    row_index = 0
    for row in grid:
        row_index += row['before']
        for column, value in enumerate(row['cells']):
            position = row_index * columns + column
            if value and position not in pictured_positions:
                lines.append(f'if (pos{index} == {position}) {{ cell{index}."Object Text" = {text_expression(value, text_files)} }}')
        row_index += 1 + row['after']
    lines.extend(checks)
    lines.extend([f'pos{index}++', '}', '}'])
    if embed_images:
        message = quote(f'Unexpected cell count in table at object {index + 1}.')
        lines.append(f'if (pos{index} != {row_count * columns}) {{ ack {message}; halt }}')
    return lines


def table_cell_pictures(index, grid, columns, text_files):
    lines = []
    checks = []
    positions = set()
    row_index = 0
    for row in grid:
        row_index += row['before']
        for column, name in row['image_files']:
            if column is None or not 0 <= column < len(row['cells']):
                raise ValueError('表格图片的单元格位置无效。')
            marker = re.search(r'(?:\bfigure\s*|图\s*)(\d+(?:[-–]\d+)?)', row['cells'][column], re.I)
            location = f'table {index + 1}, row {row_index + 1}, column {column + 1}'
            label = f'Figure {marker[1]} ({location})' if marker else f'Picture ({location})'
            position = row_index * columns + column
            positions.add(position)
            variable = f'tableBuildCell{index}'
            lines.extend([
                f'if (tableRowNumber{index} == {row_index} && tableColumnNumber{index} == {column}) {{',
                f'{variable}."Object Text" = {text_expression(row["cells"][column], text_files)}',
                embed_image(variable, name, location),
                '}',
            ])
            message = quote(f'OLE missing after table conversion: {label}\n')
            checks.append(f'if (pos{index} == {position} && !oleIsObject(cell{index})) '
                          f'{{ imageFailures++; print {message} }}')
        row_index += 1 + row['after']
    return lines, checks, positions


def write_script(path, items, native_tables=False):
    data = generate(items, native_tables=native_tables).encode('utf-8')
    with open(path, 'wb') as output:
        output.write(data)


def combine_images(pictures, max_edge=4000):
    import fitz

    with fitz.open() as document:
        pixmaps = [fitz.Pixmap(data) for data in pictures]
        width = max(picture.width for picture in pixmaps)
        height = sum(picture.height for picture in pixmaps)
        scale = min(1, max_edge / max(width, height))
        page = document.new_page(width=width * scale, height=height * scale)
        y = 0
        for picture in pixmaps:
            w, h = picture.width * scale, picture.height * scale
            page.insert_image(fitz.Rect(0, y, w, y + h), pixmap=picture)
            y += h
        return page.get_pixmap(alpha=False).tobytes('png')


def image_asset(data):
    extension = 'jpg' if data.startswith(b'\xff\xd8\xff') else 'png'
    return f'images/{sha256(data).hexdigest()}.{extension}'


def write_image_bundle(path, items):
    path = Path(path).resolve()
    asset_root = str(path.with_suffix(''))
    if not asset_root.isascii():
        asset_root = ''
    assets = {}
    text_files = {}
    prepared = []
    for item in items:
        image_files = []
        by_column = {}
        for column, data in item.get('images', ()):
            by_column.setdefault(column, []).append(data)
            assets[image_asset(data)] = data
        for column, pictures in by_column.items():
            if item.get('table_row') and column is not None:
                data = combine_images(pictures, max_edge=200)
            else:
                data = combine_images(pictures) if len(pictures) > 1 else pictures[0]
            name = image_asset(data)
            assets[name] = data
            image_files.append((column, name))
        prepared.append(dict(item, image_files=image_files))
        row = item.get('table_row')
        for text in row['cells'] if row else (item['text'],):
            if not text.isascii() and text not in text_files:
                data = text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
                name = f'text/{sha256(data).hexdigest()}.txt'
                assets[name] = data
                text_files[text] = name
    script = generate(prepared, native_tables=True, asset_root=asset_root, text_files=text_files)
    instructions = (
        '将整个 ZIP 解压到任意目录，保留 import.dxl 和图片、文字文件夹的相对位置。\n'
        '在 DOORS Classic 中以编辑模式打开空的 Formal Module，通过 Tools → Edit DXL → Load → Run 导入。\n'
        '如果出现 Locate extracted import folder 窗口，粘贴解压后包含 import.dxl 的文件夹绝对路径。'
        '请勿加引号，点击 Continue。\n'
        '核对文字、表格、图片和 DXL output，再保存模块。\n'
    )
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('import.dxl', script.encode('ascii'))
        archive.writestr('README.txt', instructions)
        for name, data in assets.items():
            archive.writestr(name, data)
    return sum(name.startswith('images/') for name in assets)


def read_script(path):
    path = Path(path)
    data = path.read_bytes()
    try:
        script = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        if sys.platform != 'win32':
            raise ValueError('无法读取 DXL 编码，请用原导出电脑将文件另存为 UTF-8。') from None
        try:
            script = data.decode('mbcs')
        except UnicodeDecodeError:
            raise ValueError('无法读取 DXL 编码，请用原导出电脑将文件另存为 UTF-8。') from None

    invalid = '只能重新打开本工具生成的 DXL。脚本结构不符合导出格式。'
    lines = [line.strip() for line in script.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]
    if len(lines) > 6 and lines[6].startswith(NATIVE_DATA):
        try:
            items = [json.loads(line[len(NATIVE_DATA):]) for line in lines if line.startswith(NATIVE_DATA)]
            if lines != generate(items, native_tables=True).split('\r\n')[:-1]:
                raise ValueError(invalid)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError(invalid) from None
        for index, item in enumerate(items, 1):
            item.update(page=f'{path.name}:对象 {index}', uncertain=True)
        return items
    items = []
    # The exporter writes a fixed six-line header, then object/text pairs and a footer.
    if len(lines) < 9 or (len(lines) - 7) % 2:
        raise ValueError(invalid)
    for offset in range(6, len(lines) - 1, 2):
        create = CREATE_OBJECT.fullmatch(lines[offset])
        assign = ASSIGN_TEXT.fullmatch(lines[offset + 1])
        index = len(items)
        if not create or not assign or create[1] != str(index) or assign[1] != str(index):
            raise ValueError(invalid)
        if create[2] == 'm':
            level = 0
        else:
            reference = int(create[3] or create[4])
            if reference >= index:
                raise ValueError(invalid)
            level = items[reference]['level'] + (create[3] is not None)
        text = re.sub(r'\\([nt"\\])', lambda match: ESCAPES[match[1]], assign[2])
        items.append(dict(text=text, level=level, page=f'{path.name}:对象 {index + 1}', uncertain=True))
    # Verify creation order and reject extra or modified DXL statements.
    try:
        canonical = generate(items).split('\r\n')[:-1]
    except ValueError:
        raise ValueError(invalid) from None
    if lines != canonical:
        raise ValueError(invalid)
    return items
