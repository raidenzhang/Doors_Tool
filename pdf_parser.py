from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
import re

from requirement_structure import (
    FRONT_TITLE, REQUIREMENT_WORDS, SECTION_PREFIX, STANDALONE_FIGURE, TABLE_CAPTION,
    TOC_ENTRY, TOC_LEADER_ONLY, TOC_TITLE, heading_key, organize_requirements, table_row_metadata, table_row_text,
)

SECTION = re.compile(r'^\d{1,3}(?:\.\d{1,3})*\.?$')
NUMBER_FRAGMENT = re.compile(r'(?:[（(]?(?:\d+|[a-zA-Z])[）)]|\d+[、．]|[•●▪◦■])')
ITEM_START = re.compile(
    r'^(?:\d{1,3}(?:\.\d{1,3})+\.?\s+|'
    r'(?:[（(]?[\da-zA-Z]+[）)]|\d+[.、])\s*|'
    r'[•●▪◦■]\s*|[-–—]\s+|\[?[A-Z][A-Z0-9_]*-\d+\]?[:：\s])'
)
LEADER = re.compile(r'[.．…·]{3,}')
PAGE_LABEL = re.compile(
    r'(\bpage\s*)\d+(?:\s*(?:of|/)\s*\d+)?|第\s*\d+\s*页',
    re.IGNORECASE,
)
PAGE_NUMBER = re.compile(r'(?:[-–—]\s*)?(\d+)(?:\s*/\s*\d+|\s*[-–—])?')


@dataclass
class Line:
    box: tuple
    text: str
    block: int
    size: float
    bold: bool
    table: bool = False
    table_row: dict | None = None
    images: list | None = None


def read_lines(page, flags):
    lines = []
    for index, block in enumerate(page.get_text('dict', flags=flags)['blocks']):
        for line in block.get('lines', []):
            spans = [span for span in line['spans'] if span['text'].strip()]
            if not spans:
                continue
            # Keep whitespace-only spans when reconstructing the original line.
            content = ''.join(span['text'] for span in line['spans']).strip()
            main = max(spans, key=lambda span: len(span['text'].strip()))
            lines.append(Line(line['bbox'], content, index, main['size'], bool(main['flags'] & 16)))
    return lines


def remove_page_furniture(pages):
    candidates = defaultdict(list)
    for number, (height, lines) in enumerate(pages, 1):
        margin = min(72, height * 0.09)
        for index, line in enumerate(lines):
            if line.table or line.images:
                continue
            top, bottom = line.box[1], line.box[3]
            if bottom <= margin:
                edge, distance = 'top', top
            elif top >= height - margin:
                edge, distance = 'bottom', height - bottom
            else:
                continue
            signature = ' '.join(line.text.casefold().split())
            bare_number = PAGE_NUMBER.fullmatch(signature)
            if bare_number:
                signature = ('page number', int(bare_number[1]) - number)
            else:
                signature = PAGE_LABEL.sub('#', signature)
            candidates[edge, signature].append((distance, number, index))

    excluded = set()
    for occurrences in candidates.values():
        occurrences.sort()
        for left, right in zip(occurrences, occurrences[1:]):
            if right[0] - left[0] <= 5 and left[1] != right[1]:
                excluded.update((left[1:], right[1:]))
    return [
        [line for index, line in enumerate(lines) if (number, index) not in excluded]
        for number, (_, lines) in enumerate(pages, 1)
    ]


def join_row_fragments(lines):
    rows = []
    for line in sorted(lines, key=lambda row: (row.box[1], row.box[0])):
        if not rows:
            rows.append(line)
            continue
        previous = rows[-1]
        left, right = sorted((previous, line), key=lambda row: row.box[0])
        lx0, ly0, lx1, ly1 = left.box
        rx0, ry0, rx1, ry1 = right.box
        height = min(ly1 - ly0, ry1 - ry0)
        overlap = min(ly1, ry1) - max(ly0, ry0)
        numbered_title = ((SECTION.fullmatch(left.text) or NUMBER_FRAGMENT.fullmatch(left.text))
                          and not SECTION.fullmatch(right.text))
        leader_page = LEADER.search(left.text) and right.text.isdecimal()
        # Limit normal stitching to nearby runs so adjacent columns stay separate.
        max_gap = max(5, left.size * 0.85)
        if numbered_title:
            max_gap = left.size * 3
        elif leader_page:
            max_gap = left.size * 5
        if height > 0 and overlap >= height * 0.72 and abs(ly1 - ry1) <= height * 0.45 and -1 <= rx0 - lx1 <= max_gap:
            style = right if numbered_title else left
            rows[-1] = replace(
                style, box=(lx0, min(ly0, ry0), rx1, max(ly1, ry1)),
                text=f'{left.text} {right.text}',
            )
        else:
            rows.append(line)
    return rows


def extract_tables(page, lines, fitz):
    figures = []
    bounds = fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
    for image in page.get_image_info():
        box = fitz.Rect(image['bbox']) & bounds
        if box.is_empty or box.width < 8 or box.height < 8 or box.get_area() >= bounds.get_area() * 0.9:
            continue
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=box, alpha=False)
        figures.append((box, pixmap.tobytes('png')))
    tables = list(page.find_tables(strategy='lines_strict').tables)
    # Use text-derived cells only when a nearby table caption confirms the region.
    captions = [line for line in lines if TABLE_CAPTION.fullmatch(line.text)]
    if captions:
        for candidate in page.find_tables(strategy='text').tables:
            rect = fitz.Rect(candidate.bbox)
            if (any(rect.intersects(fitz.Rect(table.bbox)) for table in tables)
                    or candidate.row_count < 2 or candidate.col_count < 2):
                continue
            if any((0 <= caption.box[1] - rect.y1 <= 28 or 0 <= rect.y0 - caption.box[3] <= 28)
                   and rect.x0 - 20 <= caption.box[0] <= rect.x1 for caption in captions):
                tables.append(candidate)

    table_lines = []
    regions = []
    for table in tables:
        rows = [[cell or '' for cell in row] for row in table.extract()]
        row_images = defaultdict(list)
        remaining_figures = []
        layouts = table.rows
        for box, data in figures:
            center = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            destination = next(
                ((row_index, column) for row_index, layout in enumerate(layouts)
                 for column, cell in enumerate(layout.cells) if cell and fitz.Rect(cell).contains(center)),
                None,
            )
            if destination is None:
                remaining_figures.append((box, data))
            else:
                row_index, column = destination
                row_images[row_index].append((column, data))
                if not rows[row_index][column].strip():
                    rows[row_index][column] = '[图片]'
        figures = remaining_figures
        metadata = table_row_metadata(rows)
        if not metadata:
            continue
        for index, layout in enumerate(layouts):
            if index in metadata:
                table_lines.append(Line(tuple(layout.bbox), table_row_text(rows[index]), -1, 0, False,
                                        table=True, table_row=metadata[index], images=row_images.get(index)))
        regions.append(fitz.Rect(table.bbox))
    outside = []
    for line in lines:
        x0, y0, x1, y1 = line.box
        center = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if not any(region.contains(center) for region in regions):
            outside.append(line)
    figure_lines = [Line(tuple(box), '[图片]', -1, 0, False, images=[(None, data)]) for box, data in figures]
    return sorted(join_row_fragments(outside) + table_lines + figure_lines,
                  key=lambda line: (line.box[1], line.box[0]))


def document_outline(pages, bookmarks):
    ranks = {(page, heading_key(title)): depth - 1 for depth, title, page in bookmarks if page > 0}
    chapter_keys = {
        heading_key(title) for _, title, page in bookmarks
        if page > 0 and (prefix := SECTION_PREFIX.match(title)) and prefix[1] == '1'
    }
    toc_ranks = {}
    excluded = set()
    in_contents = False
    for page_number, lines in enumerate(pages, 1):
        pending_number = None
        for index, line in enumerate(lines):
            text = line.text
            if line.table or line.images:
                continue
            if TOC_TITLE.fullmatch(text):
                in_contents = True
                excluded.add((page_number, index))
                continue
            entry = TOC_ENTRY.fullmatch(text) if LEADER.search(text) else None
            if entry or (in_contents and TOC_LEADER_ONLY.fullmatch(text)):
                title = entry[1].strip() if entry else LEADER.split(text, maxsplit=1)[0].strip()
                if pending_number and not SECTION_PREFIX.match(title):
                    title = f'{pending_number} {title}'
                pending_number = None
                if (prefix := SECTION_PREFIX.match(title)):
                    key = heading_key(title)
                    toc_ranks[key] = prefix[1].count('.')
                    if prefix[1] == '1':
                        chapter_keys.add(key)
                excluded.add((page_number, index))
                continue
            if in_contents and SECTION.fullmatch(text):
                pending_number = text.rstrip('.')
                excluded.add((page_number, index))
                continue
            in_contents = False
            pending_number = None
    return ranks, toc_ranks, chapter_keys, excluded


def is_continuation(first, previous, current, right_edge, gap, indent):
    if (ITEM_START.match(current.text) or SECTION.fullmatch(current.text)
            or LEADER.search(current.text) or LEADER.search(previous.text)
            or SECTION.fullmatch(previous.text)):
        return False
    if current.bold != previous.bold or abs(current.size - previous.size) > 0.75:
        return False

    x0, y0, x1, y1 = previous.box
    next_x, next_y = current.box[:2]
    height = y1 - y0
    if next_y - y0 < height * 0.5 or next_y - y1 > gap + previous.size * 0.35:
        return False
    if next_x >= x1 or current.box[2] <= x0:
        return False

    aligned = abs(next_x - x0) < indent / 2
    same_block = current.block == previous.block
    hanging = ITEM_START.match(first.text) and 0 <= next_x - first.box[0] <= indent * 2
    first_line_indent = same_block and 0 < first.box[0] - next_x <= indent * 2
    if not (aligned or hanging or first_line_indent):
        return False

    full_line = right_edge - x1 <= previous.size * 1.5 and x1 - x0 >= previous.size * 8
    sentence_end = previous.text.rstrip('”’」』"\')）】]').endswith(('.', '。', '！', '？', '!', '?', ';', '；', ':', '：'))
    lowercase = bool(re.match(r'[a-z]', current.text))
    if sentence_end:
        return full_line and same_block and previous.text.endswith('.') and lowercase
    return same_block or full_line or hanging


def parse_files(paths, gap, indent):
    import fitz

    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    results = []
    for path in paths:
        with fitz.open(path) as doc:
            bookmarks = doc.get_toc()
            pages = [(page.cropbox.height, extract_tables(page, read_lines(page, flags), fitz)) for page in doc]
        pages = remove_page_furniture(pages)
        ranks, toc_ranks, chapter_keys, excluded = document_outline(pages, bookmarks)
        chapter_pages = {heading_key(title): number for _, title, number in bookmarks
                         if number > 0 and heading_key(title) in chapter_keys}
        start = None
        for number, lines in enumerate(pages, 1):
            for index, line in enumerate(lines):
                key = heading_key(line.text)
                prefix = SECTION_PREFIX.match(line.text)
                first_heading = (
                    prefix and prefix[1] == '1' and
                    (ranks.get((number, key)) == 0
                     or (line.bold and len(line.text) <= 80 and not line.text.endswith(('.', '。', '：', ':'))))
                )
                matched_chapter = key in chapter_keys and chapter_pages.get(key, number) == number
                if ((number, index) not in excluded and not line.table
                        and (matched_chapter or first_heading)):
                    start = (number, index)
                    break
            if start:
                break

        grouped = []
        table_flags = []
        table_rows = {}
        images = {}
        numbered = set()
        sources = {}
        serial = 0
        for number, lines in enumerate(pages, 1):
            serial += 1  # A page boundary is not an ordinary adjacent-text boundary.
            lines = [
                line for index, line in enumerate(lines)
                if (number, index) not in excluded and (start is None or (number, index) >= start)
            ]
            text_lines = [line for line in lines if not line.table and not line.images]
            if not lines:
                continue
            right_edge = max((line.box[2] for line in text_lines), default=0)
            sizes = sorted(line.size for line in text_lines)
            body_size = sizes[len(sizes) // 2] if sizes else 0
            list_base = None
            previous_table = None
            first = previous = None
            previous_rank = None
            for line in lines:
                text = line.text
                if line.images and not line.table and previous is not None and not previous.table:
                    images.setdefault(grouped[-1][0], []).extend(line.images)
                    continue
                if not line.table and STANDALONE_FIGURE.fullmatch(text):
                    continue
                if (not line.table and previous_table is not None and TABLE_CAPTION.fullmatch(text)
                        and not REQUIREMENT_WORDS.search(text)
                        and 0 <= line.box[1] - previous_table.box[3] <= 48):
                    continue
                previous_table = line if line.table else None
                key = heading_key(text)
                rank = None if line.table else ranks.get((number, key), toc_ranks.get(key))
                prefix = SECTION_PREFIX.match(text)
                if rank is None and not line.table and len(text) <= 100 and not text.endswith(('.', '。', ':', '：')):
                    if FRONT_TITLE.fullmatch(key):
                        rank = 0
                    elif prefix and (line.bold or line.size >= body_size + 1):
                        rank = prefix[1].count('.')
                    elif line.bold and line.size >= body_size + 1:
                        rank = 0
                if (rank is None and previous_rank is None and previous is not None
                        and not (line.table or previous.table) and not text.endswith((':', '：'))
                        and is_continuation(first, previous, line, right_edge, gap, indent)):
                    old_serial, old_text, _, level, _ = grouped[-1]
                    grouped[-1] = (old_serial, old_text + '\n' + text, None, level, False)
                    previous = line
                    continue
                serial += 1
                level = 0
                if not line.table and rank is None and ITEM_START.match(text):
                    if list_base is None or line.box[0] < list_base:
                        list_base = line.box[0]
                    level = max(0, round((line.box[0] - list_base) / indent))
                    numbered.add(serial)
                else:
                    list_base = None
                sources[serial] = f'{Path(path).name}:{number}'
                grouped.append((serial, text, rank, level, False))
                table_flags.append(line.table)
                if line.table_row is not None:
                    table_rows[serial] = line.table_row
                if line.images:
                    images[serial] = line.images
                first = line
                previous = line
                previous_rank = rank
        results.extend(organize_requirements(grouped, table_flags, {}, numbered, sources.__getitem__, table_rows, images))
    return results
