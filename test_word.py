import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from word_parser import parse_word

class WordTests(unittest.TestCase):
    def test_paragraphs_tables_and_levels(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>父需求</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:pPr><w:numPr><w:ilvl w:val="1"/></w:numPr></w:pPr><w:r><w:t>Child</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.docx'
            with ZipFile(p,'w') as z: z.writestr('word/document.xml',xml)
            items=parse_word(p,12)
        self.assertEqual([i['text'] for i in items],['父需求','Child'])
        self.assertEqual([i['level'] for i in items],[0,1])
        self.assertIn('段落 2',items[1]['page'])

if __name__ == '__main__': unittest.main()
