import csv
import re
import struct
import sys
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from requirement_structure import table_row_text


def build_time_label(executable):
    try:
        with open(executable, 'rb') as binary:
            if binary.read(2) != b'MZ':
                return '构建时间未知'
            binary.seek(0x3C)
            pe_offset, = struct.unpack('<I', binary.read(4))
            binary.seek(pe_offset)
            if binary.read(4) != b'PE\0\0':
                return '构建时间未知'
            binary.seek(4, 1)
            timestamp, = struct.unpack('<I', binary.read(4))
        if timestamp:
            beijing = timezone(timedelta(hours=8))
            return datetime.fromtimestamp(timestamp, beijing).strftime('构建时间 %Y-%m-%d %H:%M:%S（北京时间）')
    except (OSError, struct.error, OverflowError, ValueError):
        pass
    return '构建时间未知'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('DOORS 需求整理工具 V2.3')
        self.geometry('1100x700')
        build_label = build_time_label(sys.executable) if getattr(sys, 'frozen', False) else '源码运行'
        footer = ttk.Frame(self)
        footer.pack(side='bottom', anchor='e', padx=10, pady=(0, 6))
        ttk.Label(footer, text=f'版本 V2.3  |  作者：Raiden.Zhang  |  {build_label}').pack(side='left')
        ttk.Button(footer, text='更新说明', command=self.show_changelog).pack(side='left', padx=(8, 0))
        self.changelog_window = None
        self.items = []
        self.paths = []
        file_bar = ttk.Frame(self)
        file_bar.pack(fill='x', padx=8, pady=(8, 4))
        export_group = ttk.Frame(file_bar)
        export_group.pack(side='right')
        ttk.Button(export_group, text='导出 CSV', command=self.export).pack(side='left', padx=2)
        ttk.Button(export_group, text='导出 DXL', command=self.export_dxl).pack(side='left', padx=2)
        ttk.Button(export_group, text='导出表格 DXL', command=lambda: self.export_dxl(True)).pack(side='left', padx=2)
        ttk.Button(export_group, text='导出含图 ZIP', command=self.export_image_bundle).pack(side='left', padx=2)
        import_group = ttk.Frame(file_bar)
        import_group.pack(side='left')
        ttk.Button(import_group, text='选择文档', command=self.select).pack(side='left', padx=2)
        ttk.Button(import_group, text='解析', command=self.parse).pack(side='left', padx=2)
        ttk.Label(import_group, text='行距阈值').pack(side='left', padx=(12, 2))
        self.gap = tk.StringVar(value='5')
        ttk.Entry(import_group, textvariable=self.gap, width=5).pack(side='left')
        ttk.Label(import_group, text='缩进阈值').pack(side='left', padx=(8, 2))
        self.indent = tk.StringVar(value='12')
        ttk.Entry(import_group, textvariable=self.indent, width=5).pack(side='left')

        edit_bar = ttk.Frame(self)
        edit_bar.pack(fill='x', padx=8, pady=(0, 6))
        for label, action in [
            ('保存修改', self.save), ('升级', lambda: self.level(-1)), ('降级', lambda: self.level(1)),
            ('合并需求', self.merge), ('按换行拆分', self.split), ('删除所选', self.delete_selected),
        ]:
            ttk.Button(edit_bar, text=label, command=action).pack(side='left', padx=2)
        search_bar = ttk.Frame(self)
        search_bar.pack(fill='x', padx=10, pady=(0, 6))
        ttk.Label(search_bar, text='搜索正文或 ID').pack(side='left')
        self.search_query = tk.StringVar()
        self.search_status = tk.StringVar()
        self.search_index = None
        self.search_query.trace_add('write', self.reset_search)
        self.search_entry = ttk.Entry(search_bar, textvariable=self.search_query, width=32)
        self.search_entry.pack(side='left', padx=6)
        ttk.Button(search_bar, text='上一条', command=lambda: self.find_requirement(-1)).pack(side='left', padx=2)
        ttk.Button(search_bar, text='下一条', command=self.find_requirement).pack(side='left', padx=2)
        ttk.Label(search_bar, textvariable=self.search_status).pack(side='left', padx=8)
        self.search_entry.bind('<Return>', self.find_next)
        self.search_entry.bind('<Shift-Return>', self.find_previous)
        self.bind('<Control-f>', self.focus_search)
        self.info = tk.StringVar(value='请选择 PDF、Word、Excel 或本工具导出的 DXL。'); ttk.Label(self, textvariable=self.info).pack(fill='x', padx=10)
        frame = ttk.Frame(self); frame.pack(fill='both', expand=True, padx=8, pady=5)
        self.tree = ttk.Treeview(frame, columns=('id','level','page','flag'), show='tree headings')
        self.tree.heading('#0', text='需求及层级'); self.tree.heading('id', text='临时 ID'); self.tree.heading('level', text='层级'); self.tree.heading('page', text='来源页'); self.tree.heading('flag', text='待确认')
        self.tree.column('#0', width=650); self.tree.column('id', width=90); self.tree.column('level', width=55); self.tree.column('page', width=100); self.tree.column('flag', width=70)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y'); self.tree.bind('<<TreeviewSelect>>', self.selected)
        self.editor_hint = tk.StringVar(value='选中后可编辑需求原文，点击“保存修改”')
        ttk.Label(self, textvariable=self.editor_hint).pack(anchor='w', padx=10)
        self.editor = tk.Text(self, height=6, wrap='word'); self.editor.pack(fill='x', padx=8, pady=(0,8))

    def show_changelog(self):
        if self.changelog_window is not None and self.changelog_window.winfo_exists():
            self.changelog_window.lift()
            self.changelog_window.focus_set()
            return
        try:
            changelog = Path(__file__).with_name('CHANGELOG.md').read_text(encoding='utf-8-sig')
        except OSError as error:
            return messagebox.showerror('更新说明', f'无法读取版本更新记录。\n{error}')

        window = tk.Toplevel(self)
        self.changelog_window = window
        window.title('更新说明')
        window.geometry('760x540')
        window.minsize(440, 280)
        window.transient(self)
        window.bind('<Escape>', lambda event: window.destroy())
        body = ttk.Frame(window, padding=12)
        body.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(body, orient='vertical')
        text = tk.Text(body, wrap='word', padx=8, pady=8, yscrollcommand=scroll.set)
        scroll.configure(command=text.yview)
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        text.tag_configure('heading', font=('Microsoft YaHei UI', 11, 'bold'), spacing1=4)
        for line in changelog.splitlines():
            heading = line.startswith('#')
            display = line.lstrip('# ') if heading else line
            if display.startswith('- '):
                display = '• ' + display[2:]
            display = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', display).replace('`', '')
            text.insert('end', display + '\n', 'heading' if heading else ())
        text.configure(state='disabled')
        text.focus_set()

    def select(self):
        paths = filedialog.askopenfilenames(filetypes=[
            ('支持的文件', '*.pdf *.docx *.xlsx *.xlsm *.xls *.dxl'), ('PDF 文件', '*.pdf'),
            ('Word 文件', '*.docx'), ('Excel 文件', '*.xlsx *.xlsm *.xls'), ('本工具导出的 DXL', '*.dxl'),
        ])
        if paths: self.paths = list(paths); self.info.set('已选择 ' + str(len(paths)) + ' 个文件')

    def parse(self):
        if not self.paths: return messagebox.showwarning('提示','请先选择 PDF、DOCX、Excel 或本工具导出的 DXL 文件。')
        if self.items and not messagebox.askyesno('重新解析','重新解析将丢弃当前修改，继续吗？'): return
        try:
            from pdf_parser import parse_files
            gap, indent = float(self.gap.get()), float(self.indent.get())
            if gap < 0 or indent <= 0: raise ValueError('行距必须大于等于 0，缩进必须大于 0')
            from word_parser import parse_word
            from dxl_export import read_script
            parsed = []
            for path in self.paths:
                suffix = Path(path).suffix.lower()
                if suffix == '.pdf': parsed.extend(parse_files([path], gap, indent))
                elif suffix == '.docx': parsed.extend(parse_word(path, indent))
                elif suffix in {'.xlsx', '.xlsm', '.xls'}:
                    from excel_parser import parse_excel
                    parsed.extend(parse_excel(path))
                elif suffix == '.dxl': parsed.extend(read_script(path))
                else: raise ValueError(f'不支持的文件类型：{suffix}。请将 .doc 另存为 .docx。')
            self.items = parsed
            image_count = sum(len(item.get('images', ())) for item in self.items)
            self.refresh(); self.info.set(f'识别 {len(self.items)} 条，关联图片 {image_count} 处。请检查识别结果。')
            if not self.items: messagebox.showwarning('无文字','未提取到文字；请检查文档是否为空或 PDF 是否为扫描件。')
        except Exception as e: messagebox.showerror('解析失败', str(e))

    def refresh(self, selected=None):
        self.reset_search()
        self.tree.delete(*self.tree.get_children()); stack=[]
        for i, item in enumerate(self.items):
            item['level'] = min(max(0,item['level']), len(stack))
            stack=stack[:item['level']]; parent=stack[-1] if stack else ''
            iid=str(i); self.tree.insert(parent, 'end', iid=iid, text=item['text'].replace('\n',' ')[:130], values=(f'R{i+1:05}',item['level']+1,item['page'],'是' if item['uncertain'] else ''), open=True); stack.append(iid)
        if selected is not None and self.items:
            iid=str(min(selected,len(self.items)-1)); self.tree.selection_set(iid); self.tree.see(iid)

    def reset_search(self, *_):
        self.search_index = None
        self.search_status.set('')

    def focus_search(self, event):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, 'end')
        return 'break'

    def find_next(self, event):
        self.find_requirement()
        return 'break'

    def find_previous(self, event):
        self.find_requirement(-1)
        return 'break'

    def find_requirement(self, direction=1):
        query = ' '.join(self.search_query.get().casefold().split())
        if not query:
            self.reset_search()
            return
        matches = [
            index for index, item in enumerate(self.items)
            if query in ' '.join(item['text'].casefold().split()) or query in f'r{index + 1:05}'
        ]
        if not matches:
            self.search_index = None
            self.search_status.set('未找到匹配项')
            return
        position = 0 if direction > 0 else len(matches) - 1
        if self.search_index in matches:
            position = (matches.index(self.search_index) + direction) % len(matches)
        self.search_index = matches[position]
        row = str(self.search_index)
        self.tree.selection_set(row)
        self.tree.focus(row)
        self.tree.see(row)
        self.search_status.set(f'第 {position + 1} 条，共 {len(matches)} 条')

    def index(self):
        sel=self.tree.selection(); return int(sel[0]) if sel else None
    def selected(self, event=None):
        i=self.index()
        if i is None:
            return
        item = self.items[i]
        row = item.get('table_row')
        text = item['text']
        hint = '选中后可编辑需求原文，点击“保存修改”'
        if row:
            text = '\t'.join(cell.replace('\\', '\\\\').replace('\t', '\\t') for cell in row['cells'])
            hint = f'表格行（{len(row["cells"])} 列），用 Tab 分隔单元格，保存时请保留分隔符。'
        if item.get('images'):
            hint += f'  已关联图片 {len(item["images"])} 处。'
        self.editor_hint.set(hint)
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', text)

    def save(self):
        i=self.index()
        if i is None: return
        item = self.items[i]
        row = item.get('table_row')
        value = self.editor.get('1.0', 'end-1c')
        if row:
            cells = [re.sub(r'\\([t\\])', lambda match: '\t' if match[1] == 't' else '\\', cell)
                     for cell in value.split('\t')]
            if len(cells) != len(row['cells']):
                return messagebox.showwarning('保存表格行', f'此行有 {len(row["cells"])} 列，请保留列之间的 Tab 分隔符。')
            value = table_row_text(cells)
            if value:
                row['cells'] = cells
        else:
            value = value.strip()
        if not value: return messagebox.showwarning('提示','需求内容不能为空。')
        item['text']=value; item['uncertain']=False; self.refresh(i)
    def level(self, delta):
        i=self.index()
        if i is None: return
        new=self.items[i]['level']+delta
        if new < 0 or (delta > 0 and (i == 0 or new > self.items[i-1]['level']+1)): return messagebox.showwarning('提示','无法调整到该层级。')
        self.items[i]['level']=new; self.items[i]['uncertain']=False; self.refresh(i)
    def delete_selected(self):
        selected = {int(row) for row in self.tree.selection()}
        if not selected:
            return messagebox.showwarning('删除需求', '请选中需要删除的需求。')
        first = min(selected)
        count = len(selected)
        prompt = f'删除需求 R{first + 1:05}？' if count == 1 else f'删除所选的 {count} 条需求？'
        prompt += '\n未选中的子需求会保留，并调整到最近的保留父项下。'
        if not messagebox.askyesno('删除需求', prompt):
            return
        remaining = []
        # At each original depth, track how many ancestors are retained.
        kept_depths = [0]
        for index, item in enumerate(self.items):
            level = item['level']
            del kept_depths[level + 1:]
            kept_depth = kept_depths[-1]
            if index in selected:
                kept_depths.append(kept_depth)
            else:
                item['level'] = kept_depth
                remaining.append(item)
                kept_depths.append(kept_depth + 1)
        self.items = remaining
        self.refresh(first)
        if not self.items:
            self.editor.delete('1.0', 'end')
        self.info.set(f'已删除 {count} 条需求，剩余 {len(self.items)} 条。')

    def merge(self):
        selected = sorted(int(row) for row in self.tree.selection())
        if not selected:
            return messagebox.showwarning('合并需求', '请选择一条需求或相邻两条需求。')
        first = selected[0]
        second = first + 1
        if len(selected) > 2 or (len(selected) == 2 and selected[1] != second):
            return messagebox.showwarning('合并需求', '请选择相邻两条需求。')
        if second >= len(self.items):
            return messagebox.showwarning('合并需求', '所选需求后没有下一条。')
        first_item, second_item = self.items[first:second + 1]
        if 'table_row' in first_item or 'table_row' in second_item:
            if not messagebox.askyesno('合并需求', '合并后，这两条的内容将成为普通需求，无法按单元格导出。继续吗？'):
                return
            first_item.pop('table_row', None)
        images = [*first_item.get('images', ()), *second_item.get('images', ())]
        if images:
            first_item['images'] = [(None, data) for _, data in images]
        left = first_item['text'].rstrip()
        right = second_item['text'].lstrip()
        boundary = left[-1:] + right[:1]
        separator = '' if re.fullmatch(r'[\u3400-\u9fff，。；：！？、]{2}', boundary) else ' '
        first_item['text'] = left + separator + right
        first_item['uncertain'] = True

        old_level = second_item['level']
        level_shift = first_item['level'] - old_level
        for index in range(second + 1, len(self.items)):
            child = self.items[index]
            if child['level'] <= old_level:
                break
            child['level'] += level_shift
        del self.items[second]
        self.refresh(first)
        self.info.set(f'已将两条需求合并为一条，剩余 {len(self.items)} 条。')

    def split(self):
        i=self.index()
        if i is None: return
        lines=[x.strip() for x in self.editor.get('1.0','end-1c').splitlines() if x.strip()]
        if len(lines)<2: return messagebox.showwarning('提示','请在编辑框中用换行分隔至少两条需求。')
        original=self.items[i]
        if 'table_row' in original:
            if not messagebox.askyesno('拆分需求', '拆分后，这一行将变为普通需求，无法按单元格导出。继续吗？'):
                return
            original = {key: value for key, value in original.items() if key != 'table_row'}
        rows = [dict(original, text=line, uncertain=True) for line in lines]
        if original.get('images'):
            rows[0]['images'] = [(None, data) for _, data in original['images']]
            for row in rows[1:]:
                del row['images']
        self.items[i:i+1] = rows
        self.refresh(i)

    def export_image_bundle(self):
        if not self.items:
            return messagebox.showwarning('导出含图 ZIP', '没有可导出的需求。')
        path = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('DOORS 导入包', '*.zip')])
        if not path:
            return
        try:
            from dxl_export import write_image_bundle
            count = write_image_bundle(path, self.items)
            messagebox.showinfo('导出完成', f'导入包已生成，包含 {count} 个图片文件。\n'
                                 '解压 ZIP 后，在 DOORS 空模块运行 import.dxl。若提示定位目录，粘贴包含 import.dxl 的文件夹路径。')
        except (OSError, ValueError) as error:
            messagebox.showerror('导出失败', str(error))

    def export_dxl(self, native_tables=False):
        if not self.items: return messagebox.showwarning('提示','没有可导出的需求。')
        if not messagebox.askyesno('导出 DXL','请先保存并检查所有修改。生成的脚本只能用于空的测试模块，运行后请检查结果。继续吗？'): return
        path=filedialog.asksaveasfilename(defaultextension='.dxl',filetypes=[('DXL 脚本','*.dxl')])
        if not path: return
        try:
            from dxl_export import write_script
            write_script(path, self.items, native_tables=native_tables)
            messagebox.showinfo('完成','DXL 已生成。请在 DOORS 空的测试模块中通过 Tools > Edit DXL 运行并验证。')
        except Exception as e: messagebox.showerror('导出失败',str(e))

    def export(self):
        if not self.items: return messagebox.showwarning('提示','没有可导出的需求。')
        if not messagebox.askyesno('确认导出','请确认已检查文本及层级。导出 CSV 后仍需在测试环境验证导入。继续吗？'): return
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV 文件','*.csv')])
        if not path: return
        try:
            stack=[]
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f); w.writerow(['Object Text','Temporary ID','Parent ID','Level','Source Page'])
                for i,item in enumerate(self.items):
                    stack=stack[:item['level']]; ident=f'R{i+1:05}'; w.writerow([item['text'],ident,stack[-1] if stack else '',item['level']+1,item['page']]); stack.append(ident)
            messagebox.showinfo('完成','CSV 已导出。DOORS 层级导入脚本尚待在真实环境验证。')
        except Exception as e: messagebox.showerror('导出失败',str(e))

if __name__ == '__main__': App().mainloop()
