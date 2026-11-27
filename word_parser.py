"""Extract editable paragraphs from DOCX without Word or external libraries."""
from pathlib import Path
import posixpath
import re
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

from requirement_structure import (
    HEADING_STYLE, ITEM_START, REQUIREMENT_WORDS, SECTION_PREFIX, STANDALONE_FIGURE,
    TABLE_CAPTION, TOC_ENTRY, TOC_LEADER, TOC_LEADER_ONLY, TOC_NUMBER, TOC_STYLE,
    TOC_TITLE, heading_key, organize_requirements, table_row_metadata, table_row_text, toc_block,
)


W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DRAWING = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def embedded_images(archive, document):
    relationships = 'word/_rels/document.xml.rels'
    if relationships not in archive.namelist():
        return {}
    targets = {}
    for relation in ET.fromstring(archive.read(relationships)):
        target = relation.get('Target', '')
        if relation.get('Type', '').endswith('/image') and relation.get('TargetMode') != 'External':
            name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'word/' + target)
            if name.startswith('word/media/'):
                targets[relation.get('Id')] = name
    images = {}
    for blip in document.iter(DRAWING+'blip'):
        key = blip.get(REL+'embed')
        if key in targets and key not in images and targets[key] in archive.namelist():
            data = archive.read(targets[key])
            if data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                images[key] = data
    return images


def looks_like_title(paragraph, text):
    if len(text) > 100 or '\n' in text or text.endswith(('.', '。', '；', ';', '！', '？', '!', '?', ':', '：')):
        return False
    runs = [run for run in paragraph.iter(W+'r')
            if any((node.text or '').strip() for node in run.findall(W+'t'))]
    bold = [run.find(f'{W}rPr/{W}b') for run in runs]
    return bool(bold) and all(node is not None and node.get(W+'val') not in {'0', 'false', 'off'}
                              for node in bold)


def inherited_property(properties, name):
    for props in properties:
        if props is not None:
            node = props.find(W+name)
            if node is not None:
                return node
    return None


def word_value(element, name, default=None):
    child = element.find(W+name) if element is not None else None
    return child.get(W+'val', default) if child is not None else default


def format_number(value, style):
    if style == 'decimalZero':
        return f'{value:02d}'
    if style in {'upperLetter', 'lowerLetter'} and value > 0:
        repeats, letter = divmod(value - 1, 26)
        text = chr(ord('A') + letter) * (repeats + 1)
        return text if style == 'upperLetter' else text.lower()
    if style in {'upperRoman', 'lowerRoman'} and 0 < value < 4000:
        parts = []
        for base, letters in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
                              (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
                              (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
            count, value = divmod(value, base)
            parts.append(letters * count)
        text = ''.join(parts)
        return text if style == 'upperRoman' else text.lower()
    return str(value)


class WordNumbering:
    def __init__(self, root):
        self.counters = {}
        self.lists = {}
        if root is None:
            return
        abstracts = {
            node.get(W+'abstractNumId'): {level.get(W+'ilvl'): level for level in node.findall(W+'lvl')}
            for node in root.findall(W+'abstractNum')
        }
        for node in root.findall(W+'num'):
            overrides = {level.get(W+'ilvl'): level for level in node.findall(W+'lvlOverride')}
            self.lists[node.get(W+'numId')] = (abstracts.get(word_value(node, 'abstractNumId'), {}), overrides)

    def depth_for_style(self, list_id, style_id):
        abstract, _ = self.lists.get(list_id, ({}, {}))
        for depth, definition in abstract.items():
            if depth and depth.isdecimal() and word_value(definition, 'pStyle') == style_id:
                return int(depth)
        return 0

    def label(self, list_id, depth):
        if list_id not in self.lists:
            return ''
        abstract, overrides = self.lists[list_id]

        def definition(index):
            override = overrides.get(str(index))
            replacement = override.find(W+'lvl') if override is not None else None
            level = replacement if replacement is not None else abstract.get(str(index))
            start_text = word_value(override, 'startOverride', word_value(level, 'start', '1'))
            start = int(start_text) if re.fullmatch(r'-?\d+', start_text) else 1
            return level, start

        level, start = definition(depth)
        pattern = word_value(level, 'lvlText', '')
        style = word_value(level, 'numFmt', 'decimal')
        counters = self.counters.setdefault(list_id, {})
        for child_depth in list(counters):
            if child_depth > depth:
                child_level, _ = definition(child_depth)
                restart = word_value(child_level, 'lvlRestart')
                if restart is None or (restart.isdecimal() and int(restart) > 0 and depth < int(restart)):
                    del counters[child_depth]
        counters[depth] = counters.get(depth, start - 1) + 1
        if style == 'none':
            return ''
        if style == 'bullet':
            return ''.join('•' if '\ue000' <= char <= '\uf8ff' else char for char in pattern)

        def substitute(match):
            index = int(match[1]) - 1
            ancestor, initial = definition(index)
            fmt = 'decimal' if level is not None and level.find(W+'isLgl') is not None else word_value(ancestor, 'numFmt', 'decimal')
            return format_number(counters.get(index, initial), fmt)

        return re.sub(r'%([1-9])', substitute, pattern)


def parse_word(path, indent):
    try:
        with ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            image_data = embedded_images(archive, root)
            numbering = WordNumbering(ET.fromstring(archive.read('word/numbering.xml'))
                                      if 'word/numbering.xml' in archive.namelist() else None)
            styles = {}
            style_names = {}
            toc_styles = set()
            if 'word/styles.xml' in archive.namelist():
                for style in ET.fromstring(archive.read('word/styles.xml')).findall(W+'style'):
                    sid = style.get(W+'styleId')
                    ppr = style.find(W+'pPr')
                    name = style.find(W+'name')
                    if sid:
                        names = name.get(W+'val', '') if name is not None else ''
                        style_names[sid] = names
                        if TOC_STYLE.fullmatch(names):
                            toc_styles.add(sid)
                        parent = style.find(W+'basedOn')
                        styles[sid] = (ppr, parent.get(W+'val') if parent is not None else None)
    except (BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f'无法读取 Word 文档 {Path(path).name}：{e}') from e
    body = root.find(W+'body')
    if body is None: return []
    table_locations = {}
    cell_locations = {}
    cell_columns = {}
    table_grids = []
    # Keep nested cell content with its outer row.
    for table in body.iter(W+'tbl'):
        grid = {}
        for row in table.findall(W+'tr'):
            cells = []
            for cell in row.findall(W+'tc'):
                column = len(cells)
                cells.append([])
                props = cell.find(W+'tcPr')
                span = word_value(props, 'gridSpan', '1')
                if span.isdecimal():
                    cells.extend([] for _ in range(max(0, int(span) - 1)))
                for paragraph in cell.iter(W+'p'):
                    table_locations.setdefault(paragraph, row)
                    cell_locations.setdefault(paragraph, cells[column])
                    cell_columns.setdefault(paragraph, column)
            grid[row] = cells
        table_grids.append(grid)
    toc_paragraphs = {
        paragraph
        for control in body.iter(W+'sdt')
        if any(gallery.get(W+'val', '').casefold() in {'table of contents', '目录'}
               for gallery in control.findall(f'{W}sdtPr/{W}docPartObj/{W}docPartGallery'))
        for paragraph in control.iter(W+'p')
    }
    chapter_one_keys = set()
    for row in body.iter(W+'tr'):
        paragraphs = row.findall(f'{W}tc/{W}p')
        texts = [''.join(node.text or '' for node in p.iter(W+'t')).strip() for p in paragraphs]
        if any(TOC_LEADER.fullmatch(text) or TOC_LEADER_ONLY.fullmatch(text) for text in texts):
            if texts and texts[0].rstrip('.') == '1':
                for text in texts[1:]:
                    if TOC_LEADER.fullmatch(text) or TOC_LEADER_ONLY.fullmatch(text):
                        title = re.split(r'[.．…·]{3,}', text, maxsplit=1)[0]
                        if title.strip():
                            chapter_one_keys.add(heading_key(title))
            toc_paragraphs.update(
                p for p, text in zip(paragraphs, texts)
                if TOC_NUMBER.fullmatch(text) or TOC_LEADER_ONLY.fullmatch(text)
            )
    toc_field_active = False
    field_depth = 0
    headings_from_toc = {}
    paragraphs_to_import = []
    numbered_paragraphs = set()
    paragraph_images = {}
    after_table = False
    for number, paragraph in enumerate(body.iter(W+'p'), 1):
        parts=[]
        in_toc_field = toc_field_active
        for node in paragraph.iter():
            if node.tag == W+'t': parts.append(node.text or '')
            elif node.tag == W+'tab': parts.append('\t')
            elif node.tag in (W+'br', W+'cr'): parts.append('\n')
            elif node.tag == W+'instrText' and re.match(r'^\s*TOC(?:\s|$)', node.text or '', re.I):
                toc_field_active = in_toc_field = True
                field_depth = 0
            elif toc_field_active and node.tag == W+'fldChar':
                kind = node.get(W+'fldCharType')
                if kind == 'begin':
                    field_depth += 1
                elif kind == 'end':
                    if field_depth:
                        field_depth -= 1
                    else:
                        toc_field_active = False
        content=''.join(parts).strip()
        figures = [image_data[key] for blip in paragraph.iter(DRAWING+'blip')
                   if (key := blip.get(REL+'embed')) in image_data]
        if paragraph in table_locations:
            after_table = True
        if not content and not figures:
            continue
        if not content:
            content = '[图片]'
        if paragraph not in table_locations:
            if (after_table and not REQUIREMENT_WORDS.search(content)
                    and all(TABLE_CAPTION.fullmatch(line.strip())
                            for line in content.splitlines() if line.strip())):
                continue
            after_table = False
            if STANDALONE_FIGURE.fullmatch(content):
                continue
        ppr=paragraph.find(W+'pPr')
        style_id = ppr.find(W+'pStyle') if ppr is not None else None
        style_name = style_id.get(W+'val') if style_id is not None else None
        hyperlink_targets = [link.get(W+'anchor', '') for link in paragraph.iter(W+'hyperlink')]
        if (in_toc_field or paragraph in toc_paragraphs or style_name in toc_styles
                or TOC_STYLE.fullmatch(style_name or '') or TOC_TITLE.fullmatch(content)
                or any(target.casefold().startswith('_toc') for target in hyperlink_targets)
                or TOC_LEADER.fullmatch(content) or toc_block(content)):
            toc_style = TOC_STYLE.fullmatch(style_names.get(style_name, '') or style_name or '')
            toc_rank = re.search(r'\d+$', toc_style[0]) if toc_style else None
            for line in content.splitlines():
                entry = TOC_ENTRY.fullmatch(line.strip())
                title = entry[1].strip() if entry else line.strip()
                prefix = SECTION_PREFIX.match(title)
                if title and (toc_rank or (entry and prefix)):
                    rank = int(toc_rank[0]) - 1 if toc_rank else prefix[1].count('.')
                    headings_from_toc[heading_key(title)] = rank
                if prefix and prefix[1] == '1' and (entry or toc_rank or in_toc_field):
                    chapter_one_keys.add(heading_key(title))
            continue
        property_chain = [ppr]
        paragraph_style = style_name
        heading_style = None
        seen = set()
        while style_name and style_name not in seen:
            seen.add(style_name)
            heading_style = heading_style or HEADING_STYLE.fullmatch(
                style_names.get(style_name, '') or style_name
            )
            style, style_name = styles.get(style_name, (None, None))
            property_chain.append(style)
        outline = inherited_property(property_chain, 'outlineLvl')
        outline_value = outline.get(W+'val', '') if outline is not None else ''
        rank = int(outline_value) if re.fullmatch(r'[0-8]', outline_value) else None
        if outline is None and heading_style:
            rank = int(heading_style[1]) - 1

        num_properties = [props.find(W+'numPr') for props in property_chain if props is not None]
        num_id = inherited_property(num_properties, 'numId')
        list_id = num_id.get(W+'val') if num_id is not None else None
        ilvl = inherited_property(num_properties, 'ilvl')
        is_numbered = list_id not in (None, '0') or (num_id is None and ilvl is not None)
        if is_numbered or ITEM_START.match(content):
            numbered_paragraphs.add(number)
        ilvl_value = ilvl.get(W+'val', '') if ilvl is not None else ''
        list_level = int(ilvl_value) if is_numbered and re.fullmatch(r'[0-8]', ilvl_value) else 0
        if is_numbered and ilvl is None and paragraph_style:
            list_level = numbering.depth_for_style(list_id, paragraph_style)
        label = numbering.label(list_id, list_level) if is_numbered else ''
        if label and not re.match(rf'^{re.escape(label)}(?:\s|$)', content):
            content = f'{label} {content}'
        if paragraph in cell_locations:
            cell_locations[paragraph].append(content)
        if figures:
            paragraph_images[number] = [
                (cell_columns.get(paragraph), figure) for figure in figures
            ]
        title = not is_numbered and looks_like_title(paragraph, content)
        paragraphs_to_import.append((number, content, rank, list_level, title, table_locations.get(paragraph)))

    for index, (_, content, rank, _, title, location) in enumerate(paragraphs_to_import):
        prefix = SECTION_PREFIX.match(content)
        if location is None and (heading_key(content) in chapter_one_keys
                                 or (prefix and prefix[1] == '1' and (rank == 0 or title))):
            paragraphs_to_import = paragraphs_to_import[index:]
            break

    grouped = []
    table_flags = []
    table_rows = {}
    images = {}
    row_metadata = {}
    for grid in table_grids:
        rows = [['\n'.join(parts) for parts in cells] for cells in grid.values()]
        row_keys = list(grid)
        row_metadata.update((row_keys[index], meta) for index, meta in table_row_metadata(rows).items())
    last_location = None
    last_image_number = None
    for number, content, rank, list_level, title, location in paragraphs_to_import:
        if location is not None and location is last_location:
            start, text, _, first_list_level, _ = grouped[-1]
            grouped[-1] = (start, table_row_text((text, content)), None, first_list_level, False)
            if number in paragraph_images:
                images.setdefault(start, []).extend(paragraph_images[number])
        else:
            if (location is None and content == '[图片]' and number in paragraph_images and grouped
                    and last_location is None and number == (last_image_number or grouped[-1][0]) + 1):
                images.setdefault(grouped[-1][0], []).extend(paragraph_images[number])
                last_image_number = number
                continue
            if location is not None:
                content = table_row_text((content,))
                if location in row_metadata:
                    table_rows[number] = row_metadata[location]
            grouped.append((number, content, rank if location is None else None, list_level,
                            title if location is None else False))
            table_flags.append(location is not None)
            if number in paragraph_images:
                images[number] = paragraph_images[number]
        last_location = location
        last_image_number = None
    return organize_requirements(
        grouped, table_flags, headings_from_toc, numbered_paragraphs,
        lambda number: f'{Path(path).name}:段落 {number}', table_rows, images,
    )
