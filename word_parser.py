"""Extract editable paragraphs from DOCX without Word or external libraries."""
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

def parse_word(path, indent):
    try:
        with ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
            styles = {}
            if 'word/styles.xml' in archive.namelist():
                for style in ET.fromstring(archive.read('word/styles.xml')).findall(W+'style'):
                    sid = style.get(W+'styleId')
                    ppr = style.find(W+'pPr')
                    if sid and ppr is not None:
                        styles[sid] = ppr
    except (BadZipFile, KeyError, ET.ParseError) as e:
        raise ValueError(f'无法读取 Word 文档 {Path(path).name}：{e}') from e
    results = []
    body = root.find(W+'body')
    if body is None: return results
    for number, paragraph in enumerate(body.iter(W+'p'), 1):
        parts=[]
        for node in paragraph.iter():
            if node.tag == W+'t': parts.append(node.text or '')
            elif node.tag == W+'tab': parts.append('\t')
            elif node.tag in (W+'br', W+'cr'): parts.append('\n')
        content=''.join(parts).strip()
        if not content: continue
        ppr=paragraph.find(W+'pPr')
        style_id = ppr.find(W+'pStyle') if ppr is not None else None
        style = styles.get(style_id.get(W+'val')) if style_id is not None else None
        num = ppr.find(W+'numPr') if ppr is not None else None
        if num is None and style is not None: num=style.find(W+'numPr')
        ilvl = num.find(W+'ilvl') if num is not None else None
        ind = ppr.find(W+'ind') if ppr is not None else None
        if ind is None and style is not None: ind=style.find(W+'ind')
        try:
            level = int(ilvl.get(W+'val', '0')) if ilvl is not None else max(0, round(int(ind.get(W+'left', ind.get(W+'start', '0'))) / 20 / indent)) if ind is not None else 0
        except ValueError: level=0
        results.append(dict(text=content, level=level, page=f'{Path(path).name}:段落 {number}', uncertain=True))
    return results
