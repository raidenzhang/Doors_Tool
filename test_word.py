import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from base64 import b64decode
from dxl_export import generate, write_image_bundle
from word_parser import parse_word

class WordTests(unittest.TestCase):
    def test_word_image_bundle_preserves_object_and_cell_association(self):
        picture = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB9sAAAAASUVORK5CYII=')
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>系统示意图。</w:t></w:r></w:p>
            <w:p><w:r><w:drawing><a:blip r:embed="pic"/></w:drawing></w:r></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>Diagram</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:drawing><a:blip r:embed="pic"/></w:drawing></w:r></w:p></w:tc>
            </w:tr></w:tbl>
          </w:body></w:document>'''
        relations = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="pic" Target="media/image.png"
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/>
        </Relationships>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.docx'
            bundle = Path(directory) / 'image package.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
                archive.writestr('word/_rels/document.xml.rels', relations)
                archive.writestr('word/media/image.png', picture)
            items = parse_word(path, 12)
            self.assertEqual([item['images'] for item in items], [[(None, picture)], [(1, picture)]])
            self.assertEqual(write_image_bundle(bundle, items), 2)
            with ZipFile(bundle) as archive:
                images = [name for name in archive.namelist() if name.startswith('images/')]
                self.assertIn(picture, [archive.read(name) for name in images])
                script = archive.read('import.dxl').decode('ascii')
                self.assertIn('embedBundleImage(obj0,', script)
                self.assertIn('embedBundleImage(tableBuildCell1,', script)
                self.assertNotIn('embedBundleImage(cell1,', script)
                self.assertLess(script.index('embedBundleImage(tableBuildCell1,'), script.index('toTable(tableObj1)'))
                self.assertIn('if (pos1 == 1 && !oleIsObject(cell1))', script)
                self.assertLess(script.index('canOpenFile'), script.index('Object obj0'))
                self.assertLess(script.index('block bundleFolderDialog'), script.index('Object obj0'))
                self.assertLess(script.index('if (!bundleFolderAccepted) halt'), script.index('Object obj0'))
                self.assertIn('assetRoot = get bundleFolderField', script)
                self.assertIn('image package', script.splitlines()[0])
                self.assertIn('readFile((assetRoot ', script)
                self.assertIn(', 65001)', script)
                self.assertIn('Object tableObj1 = obj1', script)
                self.assertIn('tableRowNumber1 < 1', script)
                self.assertIn('tableColumnNumber1 < 2', script)
                self.assertIn('toTable(tableObj1)', script)
                self.assertNotIn('table(below(', script)
                self.assertNotIn('hardDelete obj1', script)
                self.assertIn('string details = lastError()', script)
                payloads = [archive.read(name).decode('utf-8') for name in archive.namelist() if name.startswith('text/')]
                self.assertCountEqual(payloads, ['系统示意图。', '[图片]'])

    def test_word_keeps_automatic_list_numbers_and_restarts(self):
        namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        paragraphs = [
            (7, 0, 'First'), (7, 1, 'Child'), (7, 0, 'Second'),
            (7, 1, 'Child after restart'), (8, 0, 'Separate list'),
        ]
        body = ''.join(
            f'<w:p><w:pPr><w:numPr><w:ilvl w:val="{depth}"/><w:numId w:val="{list_id}"/>'
            f'</w:numPr></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
            for list_id, depth, text in paragraphs
        )
        numbering = f'''<w:numbering xmlns:w="{namespace}">
          <w:abstractNum w:abstractNumId="4">
            <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
            <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1.%2)"/></w:lvl>
          </w:abstractNum>
          <w:num w:numId="7"><w:abstractNumId w:val="4"/></w:num>
          <w:num w:numId="8"><w:abstractNumId w:val="4"/><w:lvlOverride w:ilvl="0">
            <w:startOverride w:val="5"/></w:lvlOverride></w:num>
        </w:numbering>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>')
                archive.writestr('word/numbering.xml', numbering)
            items = parse_word(path, 12)
        self.assertEqual([item['text'] for item in items],
                         ['1. First', '1.a) Child', '2. Second', '2.a) Child after restart', '5. Separate list'])
        self.assertEqual([item['level'] for item in items], [0, 1, 0, 1, 0])

    def test_rejoins_multiple_sentence_fragments_without_crossing_requirement_starts(self):
        texts = [
            '1. 控制器在自动制动模式下应满足',
            '以下响应时间限制，并在',
            '检测到故障时发出告警。',
            '2. 控制器应记录故障的时间',
            '控制器必须将故障码保存到内存。',
            'The controller shall log the warning and',
            'keep the log available for',
            'later review.',
        ]
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + ''.join(f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in texts)
            + '</w:body></w:document>'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            items = parse_word(path, 12)
        self.assertEqual([item['text'] for item in items], [
            ''.join(texts[:3]),
            texts[3],
            texts[4],
            ' '.join(texts[5:]),
        ])
        self.assertEqual(items[0]['page'], 'sample.docx:段落 1')

    def test_filters_figure_and_table_labels_and_rejoins_requirement_fragments(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Figure 1 图1</w:t></w:r></w:p>
            <w:p><w:r><w:t>figure2</w:t></w:r></w:p>
            <w:p><w:r><w:t>图 ３</w:t></w:r></w:p>
            <w:p><w:r><w:t>Figure 1 Notes 图1注释：</w:t></w:r></w:p>
            <w:p><w:r><w:t>参见图1和表1，制动速度应满足设计限制。</w:t></w:r></w:p>
            <w:p><w:r><w:t>性能要求如下：</w:t></w:r></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>响应时间</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>小于 250 ms</w:t></w:r></w:p></w:tc>
            </w:tr></w:tbl>
            <w:p><w:r><w:t>table8/表8</w:t></w:r></w:p>
            <w:p><w:r><w:t>表2</w:t></w:r></w:p>
            <w:p><w:r><w:t>Table 3 ／ 表3</w:t></w:r></w:p>
            <w:p><w:r><w:t>Table 8: day/night range</w:t><w:br/><w:t>表8：昼夜分布</w:t></w:r></w:p>
            <w:p><w:r><w:t>Table 9: J1939 Message</w:t></w:r></w:p>
            <w:p><w:r><w:t>表9：J1939报文</w:t></w:r></w:p>
            <w:p><w:r><w:t>（响应时间由控制器记录）</w:t></w:r></w:p>
            <w:p><w:r><w:t>系统应另外保存故障记录。</w:t></w:r></w:p>
            <w:p><w:r><w:t>对测试用例的要求：</w:t></w:r></w:p>
            <w:p><w:r><w:t>1. For Vego = 40 kph，直到卡车刹车停止，性能要求应满足上表的要</w:t></w:r></w:p>
            <w:p><w:r><w:t>求。</w:t></w:r></w:p>
            <w:p><w:r><w:t>2. For Vego = 60 kph，直到卡车刹车停止，性能要求应满足上表的要</w:t></w:r></w:p>
            <w:p><w:r><w:t>求。</w:t></w:r></w:p>
            <w:p><w:r><w:t>3. For Vego = 80 kph，性能要求应满足上表的要求。</w:t></w:r></w:p>
            <w:p><w:r><w:t>性能需求如下:</w:t></w:r></w:p>
            <w:p><w:r><w:t>制动响应时间应小于 150 ms。</w:t></w:r></w:p>
          </w:body></w:document>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            items = parse_word(path, 12)
        self.assertEqual([item['text'] for item in items], [
            'Figure 1 Notes 图1注释：',
            '参见图1和表1，制动速度应满足设计限制。',
            '性能要求如下：',
            '响应时间 小于 250 ms',
            '（响应时间由控制器记录）',
            '系统应另外保存故障记录。',
            '对测试用例的要求：',
            '1. For Vego = 40 kph，直到卡车刹车停止，性能要求应满足上表的要求。',
            '2. For Vego = 60 kph，直到卡车刹车停止，性能要求应满足上表的要求。',
            '3. For Vego = 80 kph，性能要求应满足上表的要求。',
            '性能需求如下:',
            '制动响应时间应小于 150 ms。',
        ])
        self.assertEqual([item['level'] for item in items], [0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1])
        self.assertEqual(items[7]['page'], 'sample.docx:段落 18')

    def test_table_caption_filter_preserves_body_and_cell_text(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Table 8: parameters mentioned in the earlier section</w:t></w:r></w:p>
            <w:p><w:r><w:t>table8/表8</w:t></w:r></w:p>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table 9</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
            <w:p/>
            <w:p><w:r><w:t>Table 9: J1939 Message</w:t></w:r></w:p>
            <w:p><w:r><w:t>表9：控制器应按规定发送报文。</w:t></w:r></w:p>
            <w:p><w:r><w:t>Table 9: cross-reference</w:t></w:r></w:p>
          </w:body></w:document>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            items = parse_word(path, 12)
        self.assertEqual([item['text'] for item in items], [
            'Table 8: parameters mentioned in the earlier section', 'table8/表8',
            'Table 9', '表9：控制器应按规定发送报文。', 'Table 9: cross-reference',
        ])

    def test_import_starts_at_chapter_one_and_keeps_each_table_row_together(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Cover Page</w:t></w:r></w:p>
            <w:p><w:r><w:t>Document number: 123</w:t></w:r></w:p>
            <w:p><w:r><w:t>1 General Functions ........ 8</w:t></w:r></w:p>
            <w:p><w:r><w:t>Introduction</w:t></w:r></w:p>
            <w:p><w:r><w:t>Background information.</w:t></w:r></w:p>
            <w:p><w:r><w:t>History</w:t></w:r></w:p>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Old revision</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
            <w:p><w:r><w:t>Glossary</w:t></w:r></w:p>
            <w:p><w:r><w:t>Abbreviation definition</w:t></w:r></w:p>
            <w:p><w:r><w:t>General Functions</w:t></w:r></w:p>
            <w:p><w:r><w:t>The system shall apply the limits in the table.</w:t></w:r></w:p>
            <w:tbl>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Parameter</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Speed</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>60</w:t><w:br/><w:t>km/h</w:t></w:r></w:p>
                      <w:p><w:r><w:t>Maximum</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr>
              <w:tr><w:tc><w:p><w:r><w:t>History</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr>
            </w:tbl>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Second table</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          </w:body></w:document>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
            items = parse_word(path, 12)
        self.assertEqual([item['text'] for item in items], [
            'General Functions',
            'The system shall apply the limits in the table.',
            'Parameter Value',
            'Speed 60 km/h Maximum',
            'History',
            'Second table',
        ])
        self.assertEqual([item['level'] for item in items], [0, 1, 1, 1, 1, 1])
        self.assertEqual(items[3]['table_row']['cells'], ['Speed', '60\nkm/h\nMaximum'])
        self.assertEqual(items[4]['table_row']['cells'], ['History', ''])
        self.assertEqual(items[4]['table_row']['before'], 1)
        self.assertEqual(items[3]['table_row']['id'], items[4]['table_row']['id'])
        self.assertNotEqual(items[4]['table_row']['id'], items[5]['table_row']['id'])
        script = generate(items, native_tables=True)
        self.assertIn('Object obj2 = table(obj1, 4, 2)', script)
        self.assertIn('"60\\nkm/h\\nMaximum"', script)

    def test_multiline_toc_and_stable_section_hierarchy(self):
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Table of Contents 目录</w:t><w:br/>
              <w:t>1.1 Forward Collision Warning ........ 10</w:t><w:br/>
              <w:t>1.1.1 Longitudinal Object ........ 11</w:t></w:r></w:p>
            <w:p><w:pPr><w:pStyle w:val="CustomHeading"/></w:pPr><w:r><w:t>General Functions</w:t></w:r></w:p>
            <w:p><w:r><w:t>Forward Collision Warning</w:t></w:r></w:p>
            <w:p><w:pPr><w:ind w:left="480"/></w:pPr><w:r><w:t>First requirement.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Second requirement.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Longitudinal Object</w:t></w:r></w:p>
            <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr><w:r><w:t>Parent test.</w:t></w:r></w:p>
            <w:p><w:pPr><w:numPr><w:ilvl w:val="1"/></w:numPr></w:pPr><w:r><w:t>Child test.</w:t></w:r></w:p>
            <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Partial Braking</w:t></w:r></w:p>
            <w:p><w:r><w:t>Braking requirement.</w:t></w:r></w:p>
          </w:body></w:document>'''
        styles = '''<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:style w:styleId="CustomHeading"><w:basedOn w:val="RootHeading"/></w:style>
            <w:style w:styleId="RootHeading"><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
            </w:styles>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', xml)
                archive.writestr('word/styles.xml', styles)
            items = parse_word(path, 12)
        self.assertEqual([i['text'] for i in items], [
            'General Functions', 'Forward Collision Warning', 'First requirement.',
            'Second requirement.', 'Longitudinal Object', 'Parent test.', 'Child test.',
            'Partial Braking', 'Braking requirement.',
        ])
        self.assertEqual([i['level'] for i in items], [0, 1, 2, 2, 2, 3, 4, 1, 2])

    def test_word_wrap_fragments_and_header_footer_parts(self):
        namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        xml = f'''<w:document xmlns:w="{namespace}"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body>
            <w:p><w:r><w:t>Table of Contents 目录</w:t></w:r></w:p>
            <w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr><w:r><w:t>Automatic entry</w:t></w:r></w:p>
            <w:p><w:r><w:fldChar w:fldCharType="begin"/><w:instrText> TOC </w:instrText><w:fldChar w:fldCharType="separate"/></w:r></w:p>
            <w:p><w:r><w:t>Another automatic entry</w:t><w:fldChar w:fldCharType="end"/></w:r></w:p>
            <w:p><w:r><w:t>1.1 Forward Collision Warning</w:t></w:r></w:p>
            <w:p><w:r><w:t>控制器应持续监测驾驶员的制动请求</w:t></w:r></w:p>
            <w:p><w:r><w:t>并在检测到故障时发出告警。</w:t></w:r></w:p>
            <w:p><w:r><w:t>2) 记录故障</w:t><w:br/><w:t>并存储故障时间。</w:t></w:r></w:p>
            <w:p><w:r><w:t>REQ-3 Record the warning and</w:t></w:r></w:p>
            <w:p><w:r><w:t>store the timestamp.</w:t></w:r></w:p>
            <w:p><w:r><w:t>REQ-4 Clear the display.</w:t></w:r></w:p>
            <w:tbl><w:tr>
              <w:tc><w:p><w:r><w:t>1.2</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>目录标题 ........ 12</w:t></w:r></w:p></w:tc>
            </w:tr></w:tbl>
            <w:sectPr><w:headerReference w:type="default" r:id="rId1"/>
              <w:footerReference w:type="default" r:id="rId2"/></w:sectPr>
          </w:body></w:document>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('[Content_Types].xml', '''<Types
                    xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                    <Default Extension="xml" ContentType="application/xml"/>
                    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                    <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
                    <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
                    </Types>''')
                archive.writestr('_rels/.rels', '''<Relationships
                    xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                    <Relationship Id="rId1" Target="word/document.xml"
                      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>
                    </Relationships>''')
                archive.writestr('word/document.xml', xml)
                archive.writestr('word/_rels/document.xml.rels', '''<Relationships
                    xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                    <Relationship Id="rId1" Target="header1.xml"
                      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"/>
                    <Relationship Id="rId2" Target="footer1.xml"
                      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"/>
                    </Relationships>''')
                archive.writestr('word/header1.xml', f'<w:hdr xmlns:w="{namespace}"><w:p><w:r><w:t>测试页眉</w:t></w:r></w:p></w:hdr>')
                archive.writestr('word/footer1.xml', f'<w:ftr xmlns:w="{namespace}"><w:p><w:r><w:t>测试页脚</w:t></w:r></w:p></w:ftr>')
            items = parse_word(path, 12)

        self.assertEqual([item['text'] for item in items], [
            '1.1 Forward Collision Warning',
            '控制器应持续监测驾驶员的制动请求并在检测到故障时发出告警。',
            '2) 记录故障\n并存储故障时间。',
            'REQ-3 Record the warning and store the timestamp.',
            'REQ-4 Clear the display.',
        ])
        self.assertEqual(items[1]['page'], 'sample.docx:段落 6')

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
