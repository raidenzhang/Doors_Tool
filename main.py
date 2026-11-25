import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('DOORS 需求整理工具 V0.2')
        self.geometry('1100x700')
        ttk.Label(self, text='版本 V0.2  |  作者：Raiden.Zhang  |  构建时间：2026-11-25 20:51 (北京时间)').pack(anchor='e', padx=10, pady=(4, 0))
        self.items = []
        self.paths = []
        bar = ttk.Frame(self); bar.pack(fill='x', padx=8, pady=8)
        for label, action in [('选择文档', self.select), ('解析', self.parse), ('保存修改', self.save), ('升级', lambda: self.level(-1)), ('降级', lambda: self.level(1)), ('合并下一条', self.merge), ('按换行拆分', self.split), ('导出 CSV', self.export), ('导出 DXL', self.export_dxl)]:
            ttk.Button(bar, text=label, command=action).pack(side='left', padx=2)
        ttk.Label(bar, text='行距阈值').pack(side='left', padx=(12, 2))
        self.gap = tk.StringVar(value='5'); ttk.Entry(bar, textvariable=self.gap, width=5).pack(side='left')
        ttk.Label(bar, text='缩进阈值').pack(side='left', padx=(8, 2))
        self.indent = tk.StringVar(value='12'); ttk.Entry(bar, textvariable=self.indent, width=5).pack(side='left')
        self.info = tk.StringVar(value='请选择 PDF 或 Word（.docx）文件。'); ttk.Label(self, textvariable=self.info).pack(fill='x', padx=10)
        frame = ttk.Frame(self); frame.pack(fill='both', expand=True, padx=8, pady=5)
        self.tree = ttk.Treeview(frame, columns=('id','level','page','flag'), show='tree headings')
        self.tree.heading('#0', text='需求及层级'); self.tree.heading('id', text='临时 ID'); self.tree.heading('level', text='层级'); self.tree.heading('page', text='来源页'); self.tree.heading('flag', text='待确认')
        self.tree.column('#0', width=650); self.tree.column('id', width=90); self.tree.column('level', width=55); self.tree.column('page', width=100); self.tree.column('flag', width=70)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y'); self.tree.bind('<<TreeviewSelect>>', self.selected)
        ttk.Label(self, text='选中后可编辑需求原文，点击“保存修改”').pack(anchor='w', padx=10)
        self.editor = tk.Text(self, height=6, wrap='word'); self.editor.pack(fill='x', padx=8, pady=(0,8))

    def select(self):
        paths = filedialog.askopenfilenames(filetypes=[('支持的文档','*.pdf *.docx'), ('PDF 文件','*.pdf'), ('Word 文件','*.docx')]);
        if paths: self.paths = list(paths); self.info.set('已选择 ' + str(len(paths)) + ' 个文件')

    def parse(self):
        if not self.paths: return messagebox.showwarning('提示','请先选择 PDF 或 DOCX 文件。')
        if self.items and not messagebox.askyesno('重新解析','重新解析将丢弃当前修改，继续吗？'): return
        try:
            from pdf_parser import parse_files
            gap, indent = float(self.gap.get()), float(self.indent.get())
            if gap < 0 or indent <= 0: raise ValueError('行距必须大于等于 0，缩进必须大于 0')
            from word_parser import parse_word
            parsed = []
            for path in self.paths:
                suffix = Path(path).suffix.lower()
                if suffix == '.pdf': parsed.extend(parse_files([path], gap, indent))
                elif suffix == '.docx': parsed.extend(parse_word(path, indent))
                else: raise ValueError(f'不支持的文件类型：{suffix}。请将 .doc 另存为 .docx。')
            self.items = parsed
            self.refresh(); self.info.set(f'识别 {len(self.items)} 条；请逐条检查和修改。扫描件需先转换为可选文字的 PDF。')
            if not self.items: messagebox.showwarning('无文字','未提取到文字；请检查文档是否为空或 PDF 是否为扫描件。')
        except Exception as e: messagebox.showerror('解析失败', str(e))

    def refresh(self, selected=None):
        self.tree.delete(*self.tree.get_children()); stack=[]
        for i, item in enumerate(self.items):
            item['level'] = min(max(0,item['level']), len(stack))
            stack=stack[:item['level']]; parent=stack[-1] if stack else ''
            iid=str(i); self.tree.insert(parent, 'end', iid=iid, text=item['text'].replace('\n',' ')[:130], values=(f'R{i+1:05}',item['level']+1,item['page'],'是' if item['uncertain'] else ''), open=True); stack.append(iid)
        if selected is not None and self.items:
            iid=str(min(selected,len(self.items)-1)); self.tree.selection_set(iid); self.tree.see(iid)

    def index(self):
        sel=self.tree.selection(); return int(sel[0]) if sel else None
    def selected(self, event=None):
        i=self.index()
        if i is not None: self.editor.delete('1.0','end'); self.editor.insert('1.0',self.items[i]['text'])
    def save(self):
        i=self.index()
        if i is None: return
        value=self.editor.get('1.0','end-1c').strip()
        if not value: return messagebox.showwarning('提示','需求内容不能为空。')
        self.items[i]['text']=value; self.items[i]['uncertain']=False; self.refresh(i)
    def level(self, delta):
        i=self.index()
        if i is None: return
        new=self.items[i]['level']+delta
        if new < 0 or (delta > 0 and (i == 0 or new > self.items[i-1]['level']+1)): return messagebox.showwarning('提示','无法调整到该层级。')
        self.items[i]['level']=new; self.items[i]['uncertain']=False; self.refresh(i)
    def merge(self):
        i=self.index()
        if i is None or i+1>=len(self.items): return
        self.items[i]['text'] += '\n' + self.items[i+1]['text']; self.items[i]['uncertain']=True; del self.items[i+1]; self.refresh(i)
    def split(self):
        i=self.index()
        if i is None: return
        lines=[x.strip() for x in self.editor.get('1.0','end-1c').splitlines() if x.strip()]
        if len(lines)<2: return messagebox.showwarning('提示','请在编辑框中用换行分隔至少两条需求。')
        original=self.items[i]; self.items[i:i+1]=[dict(original,text=line,uncertain=True) for line in lines]; self.refresh(i)
    def export_dxl(self):
        if not self.items: return messagebox.showwarning('提示','没有可导出的需求。')
        if not messagebox.askyesno('导出 DXL','请先保存并检查所有修改。生成的脚本只能用于空的测试模块，运行后请检查结果。继续吗？'): return
        path=filedialog.asksaveasfilename(defaultextension='.dxl',filetypes=[('DXL 脚本','*.dxl')])
        if not path: return
        try:
            from dxl_export import write_script
            write_script(path,self.items)
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
