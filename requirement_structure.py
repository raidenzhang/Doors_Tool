"""Shared requirement classification and hierarchy rules."""

import re
from uuid import uuid4


TOC_STYLE = re.compile(r'^(?:toc\s*(?:[1-9]\d*|heading)|目录\s*(?:[1-9]\d*|标题))$', re.I)
TOC_LEADER = re.compile(r'\S.*?\s*[.．…·]{3,}\s*\d+\s*$')
TOC_LEADER_ONLY = re.compile(r'\S.*?[.．…·]{3,}\s*$')
TOC_NUMBER = re.compile(r'\d+(?:\.\d+)*\.?')
TOC_TITLE = re.compile(r'^(?:table\s+of\s+contents(?:\s+目录)?|目录(?:\s+table\s+of\s+contents)?)$', re.I)
HEADING_STYLE = re.compile(r'^(?:heading|标题)\s*([1-9])$', re.I)
SECTION_PREFIX = re.compile(r'^(\d{1,3}(?:\.\d+)*)\.?\s+')
TOC_ENTRY = re.compile(r'^(.+?)(?:[.．…·]{3,}|\t+)\s*\d+\s*$')
FRONT_TITLE = re.compile(
    r'^(?:cover\s*page|封面|introduction(?:\s+简介)?|简介|引言|'
    r'(?:(?:revision|change|document)\s+)?history(?:\s+变更历史)?|'
    r'变更历史|修订历史|glossary(?:\s+术语(?:表)?)?|术语表?)$', re.I
)
LABEL_DIGITS = r'[0-9０-９]+(?:[.．-][0-9０-９]+)*'
FIGURE_NUMBER = rf'(?:fig(?:ure)?\.?|图)\s*{LABEL_DIGITS}'
STANDALONE_FIGURE = re.compile(
    rf'{FIGURE_NUMBER}(?:\s*[/／]?\s*{FIGURE_NUMBER})*\s*[.。：:]?', re.I
)
TABLE_NUMBER = rf'(?:table|表)\s*{LABEL_DIGITS}'
TABLE_CAPTION = re.compile(
    rf'{TABLE_NUMBER}(?:\s*[/／]?\s*{TABLE_NUMBER})*\s*(?:[:：]\s*.*|[.。])?', re.I
)
REQUIREMENT_WORDS = re.compile(
    r'\b(?:shall|must|should)\b|应当|必须|不得|(?<![响对适反供效感])应(?=[\u3400-\u9fff])', re.I
)
SHORT_TAIL = re.compile(r'[\u3400-\u9fff]{1,6}[。！？；][”’」』）)]*$')
ITEM_START = re.compile(r'^(?:[（(]?\d+[)）.、]\s*|[•●▪]|[A-Z][A-Z0-9_]*-\d+\b)')
PARENTHETICAL = re.compile(r'^[（(][\s\S]+[）)][。.]?$')
SENTENCE_END = re.compile(r'[。！？!?；;.:：][”’」』）)]*$')
CONTINUING_TEXT = re.compile(r'^(?:[a-z]|[，、；）】]|并且|并在|并将|并应|以及|以便|且|其中|从而)')
OPEN_CLAUSE = re.compile(r'(?:[，、,（(]|(?:\b(?:and|or|to|the|of|when|if|with|by|for|shall|must))|(?:满足|符合|确保|保持|小于|大于|根据|由于|按照|以及|以便|并且|并在|不得|应当|必须|的|应|将|要))$', re.I)


def join_requirement_continuation(previous, current):
    if SENTENCE_END.search(previous):
        return None
    if (SHORT_TAIL.fullmatch(current) and len(previous.splitlines()[-1]) >= 18
            and re.search(r'[\u3400-\u9fff]$', previous)):
        return previous + current
    if (len(previous) < 12 or not (REQUIREMENT_WORDS.search(previous) or ITEM_START.match(previous))
            or current.endswith((':', '：'))):
        return None
    if not (OPEN_CLAUSE.search(previous) or CONTINUING_TEXT.match(current)):
        return None
    if REQUIREMENT_WORDS.search(current) and not CONTINUING_TEXT.match(current):
        return None
    boundary = previous[-1:] + current[:1]
    separator = '' if re.fullmatch(r'[\u3400-\u9fff，。；：！？、]{2}', boundary) else ' '
    return previous + separator + current


def heading_key(text):
    return ' '.join(SECTION_PREFIX.sub('', text).split()).casefold()


def toc_block(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    entries = sum(bool(TOC_ENTRY.fullmatch(line) or TOC_LEADER_ONLY.fullmatch(line)) for line in lines)
    return bool(entries and (
        TOC_TITLE.fullmatch(lines[0])
        or all(TOC_ENTRY.fullmatch(line) or TOC_LEADER_ONLY.fullmatch(line)
               or TOC_NUMBER.fullmatch(line) for line in lines)
    ))


def table_row_text(cells):
    return ' '.join(word for cell in cells if cell for word in cell.split())


def table_row_metadata(rows):
    """Keep empty grid positions without showing blank requirements in the tree."""
    table_id = uuid4().hex
    width = max(map(len, rows), default=0)
    metadata = {}
    blanks = 0
    for index, cells in enumerate(rows):
        if not table_row_text(cells):
            blanks += 1
            continue
        metadata[index] = dict(id=table_id, cells=list(cells) + [''] * (width - len(cells)),
                               before=blanks, after=0)
        blanks = 0
    if metadata:
        metadata[next(reversed(metadata))]['after'] = blanks
    return metadata


def organize_requirements(grouped, table_flags, headings_from_toc, numbered_paragraphs, source_for,
                          table_rows=None, images=None):
    results = []
    heading_ranks = []
    has_structural_headings = any(
        not is_table and (rank is not None or heading_key(content) in headings_from_toc)
        for (_, content, rank, _, _), is_table in zip(grouped, table_flags)
    )
    skipping_front = False
    previous_body = None
    lead_ins = []
    for (number, content, rank, list_level, title), is_table in zip(grouped, table_flags):
        if rank is None and not is_table:
            rank = headings_from_toc.get(heading_key(content))
        if rank is None and title and not has_structural_headings:
            prefix = SECTION_PREFIX.match(content)
            rank = prefix[1].count('.') if prefix else 0
        if not is_table and FRONT_TITLE.fullmatch(heading_key(content)):
            skipping_front = rank is not None
            previous_body = None
            lead_ins.clear()
            continue
        if skipping_front and rank is None:
            continue
        skipping_front = False
        if rank is not None:
            lead_ins.clear()
            while heading_ranks and heading_ranks[-1] >= rank:
                heading_ranks.pop()
            level = len(heading_ranks)
            heading_ranks.append(rank)
        else:
            level = len(heading_ranks) + list_level
        numbered = not is_table and number in numbered_paragraphs
        if rank is None and previous_body is not None:
            previous_number, previous_list_level, previous_table = previous_body
            prior = results[-1]
            previous_text = prior['text']
            if (number == previous_number + 1 and not (previous_table or is_table or numbered)
                    and not PARENTHETICAL.fullmatch(content)):
                joined = join_requirement_continuation(previous_text, content)
                if joined is not None:
                    prior['text'] = joined
                    if images and number in images:
                        prior.setdefault('images', []).extend(images[number])
                    previous_body = (number, previous_list_level, False)
                    continue
        while lead_ins:
            parent_level, first_list_level, kind = lead_ins[-1]
            if kind is None:
                kind = 'list' if numbered else 'table' if is_table else 'text'
                first_list_level = list_level
                lead_ins[-1] = (parent_level, first_list_level, kind)
                level = parent_level + 1
                break
            if kind == 'list' and numbered and list_level >= first_list_level:
                level = parent_level + 1 + list_level - first_list_level
                break
            if is_table and kind == 'table' or not is_table and PARENTHETICAL.fullmatch(content):
                level = parent_level + 1
                break
            lead_ins.pop()
        level = min(level, results[-1]['level'] + 1) if results else 0
        item = dict(text=content, level=level, page=source_for(number), uncertain=True)
        if table_rows and number in table_rows:
            item['table_row'] = table_rows[number]
        if images and number in images:
            item['images'] = images[number].copy()
        results.append(item)
        if rank is None and not is_table and content.endswith((':', '：')):
            lead_ins.append((level, 0, None))
        previous_body = (number, list_level, is_table) if rank is None else None
    return results
