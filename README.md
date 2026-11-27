# DOORS Requirement Importer V2.3

作者 / Author: Raiden.Zhang

[版本更新记录 / Changelog](CHANGELOG.md) · [维护约定 / Maintenance](AGENTS.md)

## 中文

DOORS 需求整理工具面向 **DOORS Classic 9.7.2.11**。它在 Windows 上离线读取 Word `.docx` 和含可选文字的 PDF，支持检查、编辑需求及其父子层级，并导出 CSV 或 DXL。

### 快速开始

1. 从 [GitHub Releases](https://github.com/raidenzhang/Doors_Tool/releases/tag/v2.3) 下载并双击 `DOORS-Importer.exe`。单文件 EXE 已包含 Python 和运行依赖，右下角显示版本、作者和北京时间的构建时间，点击“更新说明”可离线查看完整版本历史。
2. 点击 **选择文档**，选中一个或多个 PDF、DOCX 或 Excel 文件，再点击 **解析**。第一行左侧是导入，右侧是导出，第二行是编辑操作。旧版 Word `.doc` 请先另存为 `.docx`。
3. 在需求树中检查文字、来源和层级，处理标为「待确认」的条目。在编辑框修改正文后，点击 **保存修改**。
4. 校对完成后，使用 **导出 DXL** 保留 DOORS 父子层级，或使用 **导出 CSV** 留存文本和层级字段。重新解析会用新结果替换当前调整。

### 搜索与编辑

要继续编辑之前导出的 DXL，点击 **选择文档** 选中本工具生成的 .dxl，再点击 **解析**。工具只读取正文和层级，修改后可重新导出。来源显示 DXL 文件名和对象序号。

| 操作 | 用法 |
| --- | --- |
| 搜索 | 按 **Ctrl+F**，输入正文关键词或临时 ID，例如 `R00012`。按 **Enter** 查找下一条，按 **Shift+Enter** 查找上一条。搜索忽略大小写。 |
| 调整层级 | 选中一条，点击 **升级** 或 **降级**。 |
| 合并 | 选中相邻两条后点击 **合并需求**。只选一条时与下一条合并。接缝处取消换行，保留第一条的来源和层级。 |
| 拆分 | 在编辑框中用换行隔开要拆出的条目，再点击 **按换行拆分**。 |
| 删除 | 用 **Ctrl** 多选或 **Shift** 连选后点击 **删除所选**。未选中的子需求会保留，并调整到最近保留的父项下。 |

### Word 和 PDF 识别

- 能匹配第 1 章标题时，从该章开始导入，跳过之前的封面、简介、变更历史和术语表。可识别的目录项会被跳过。
- 标题和编号用于确定父子层级。识别到的原文序号保留在需求正文开头，临时 ID 单独显示。「性能要求如下：」等引导段落可成为下方正文、表格或连续编号条目的父项。能识别为续文的多个片段可接回同一条需求。
- 可识别的表格按行导入，每个非空行生成一条需求，按列顺序用空格拼接，表头也保留。独立图号和紧贴表格下方的独立表号或表题会被过滤，正文引用保留。选中表格行编辑时用 Tab 分隔各格，保存时保留原列数。原生表格导出保留可识别的行列和单元格内容，合并格视觉效果和样式需人工核对。
- **Word** 使用段落、标题大纲和列表级别，跳过原生页眉页脚。来源显示原始段落序号。
- **PDF** 使用书签、文字坐标和表格边界，过滤多页重复的页眉页脚。来源显示原始页码。无边框或跨页表格、跨页续文、只出现一次的页眉页脚及复杂多栏版式需人工检查。扫描件需先转成含文字层的 PDF，工具不做 OCR。

### Com Matrix 和 UDS 的 Excel 导入

通过 **选择文档 → 解析** 打开 `.xls`、`.xlsx` 或 `.xlsm`。每个非空工作表为一个父项，每个非空行生成一条需求。列顺序和表头保留，来源显示工作表名和源行号。纵向合并的报文 ID、诊断服务等字段会补到后续有数据的行。用 **导出 DXL** 逐条导入，或者用 **导出表格 DXL** 重建表格。

工具不会执行公式或宏。XLS 读取已保存的公式结果；XLSX 和 XLSM 在没有缓存值时保留公式文本。Excel 图表和图片当前不导入。
### 导入 DOORS Classic

**保留父子层级时，使用工具导出的 `.dxl`。** 需要在 DOORS 中保留表格行列时，点击 **导出表格 DXL**。该模式会创建原生表格，保留空单元格和格内换行。普通 **导出 DXL** 仍将每行作为一条需求。

1. 在 DOORS 中新建一个**空的 Formal Module**，以编辑模式打开。脚本会拒绝已有对象的模块。
2. 在该模块窗口选择 **Tools → Edit DXL**。
3. 在 **DXL Interaction** 中点击 **Load…**，选中导出的 `.dxl`，再点击 **Run** 并确认创建对象。
4. 检查需求正文、中文字符、换行和父子层级，确认后保存模块。如果 **Run** 灰显，请联系 DOORS 管理员确认 DXL 执行权限。

DXL 文件采用 UTF-8。V2.3 已通过本地自动测试，DOORS Classic 9.7.2.11 客户端导入尚未实测。首次使用时建议先在空测试模块中导入少量脱敏需求。[IBM DOORS 9.7.2 DXL 操作说明](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.2?topic=dxl-developing-programs)

CSV 采用带 BOM 的 UTF-8，包含 `Object Text`、`Temporary ID`、`Parent ID`、`Level` 和 `Source Page`。可通过 **File → Import → Spreadsheet** 检查或导入。DOORS 的普通表格导入会把 `Parent ID` 和 `Level` 当作字段，父子层级需通过 DXL 等方式建立。

### 导入带图需求

点击 **导出含图 ZIP** 后，将 ZIP 完整解压，再在 DOORS 空模块内加载并运行 `import.dxl`。ZIP 内含 `import.dxl`、图片、UTF-8 文本和 `README.txt`。若出现 Locate extracted import folder 窗口，粘贴包含 `import.dxl` 的文件夹完整路径（不加引号），点击 Continue。脚本会在导入前检查文件，并在 DXL output 报告 OLE 嵌入失败的图片。

试用版支持 DOCX 内嵌 PNG/JPEG 和 PDF 位图。DOCX 使用段落及单元格归属，PDF 使用页面位置。同一需求或单元格里的多张图片按顺序纵向拼接，ZIP 中保留原图。表格图片先转成最长边约 200 像素、无透明通道的 PNG，按原行列嵌入后再转换为原生表格。DXL output 会报告转换后未保留的图片及其行列。跨栏和跨页图片归属需要核对。PDF 矢量图和扫描整页尚不处理，实际显示取决于目标 DOORS 客户端的 OLE 支持。本工具的 DXL 回读入口继续用于普通及原生表格 DXL，含图 ZIP 应保留原始 Word 或 PDF 以便重新解析。
### 从源码运行和构建

使用 Python 3.10+。运行 `setup.bat` 安装依赖，运行 `run.bat` 启动，通过 `python -m unittest -v` 运行测试。运行 `build.bat` 后，默认生成 `dist/DOORS-Importer.exe`。可用下列命令打包到版本目录。

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DOORS-Importer --distpath dist/V2.3 --add-data "CHANGELOG.md:." main.py
```

安装依赖需要网络或预先准备的离线包。应用运行时离线。

## English

DOORS Requirement Importer runs offline on Windows and prepares Word DOCX and text-based PDF, and XLS/XLSX/XLSM requirements for DOORS Classic 9.7.2.11. The V2.3 executable is built at `dist/V2.3/DOORS-Importer.exe`. The lower-right corner shows the build time in Beijing time (UTC+8). Click 更新说明 to view the full version history offline.

1. Select one or more documents, parse them, and review the tree, source locations, and entries marked for confirmation. Save text edits with **Save changes** (保存修改).
2. Press **Ctrl+F** to search full requirement text or a temporary ID. Use **Enter** for the next match or **Shift+Enter** for the previous one. The toolbar can change the selected item's level, merge adjacent entries, split text at line breaks, and delete multiple selected items. Unselected descendants are retained when a parent is deleted.
3. Export **DXL** to create the hierarchy in DOORS, or **CSV** to retain the text and hierarchy fields for review or spreadsheet use. Parsing again replaces current edits.

Word and PDF share rules for detecting contents, chapter 1, lead-ins, continuations, and figure or table labels. Word reads document structure and reports paragraph numbers. Detected source numbering is preserved in the requirement text. PDF uses bookmarks and layout, reports page numbers, and extracts detected table rows. Each non-empty table row, including a header row, becomes one item with its cells joined by spaces. Review borderless and multi-page tables, multi-column PDFs, and unique margin text manually. Image-only PDFs need an existing text layer.

To reopen an earlier export, use **Select document** to select a .dxl produced by this tool, then parse it. The app reads text and hierarchy without running the script.

### Import into DOORS Classic

Select **导出表格 DXL** to recreate detected Word and PDF tables as native DOORS tables, preserving cell positions, blank cells and line breaks. Regular DXL export keeps one requirement per table row. Review merged cells and formatting separately.

Open a new, empty **formal module** in edit mode. In the module window, choose **Tools → Edit DXL → Load…**, load the exported UTF-8 `.dxl`, and click **Run**. Confirm object creation, check the text and parent-child relationships, then save the module. The generated script requires an empty module. Running it in DOORS Classic 9.7.2.11 has yet to be verified. [IBM DOORS 9.7.2 DXL instructions](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.2?topic=dxl-developing-programs)

A standard CSV import treats `Parent ID` and `Level` as attribute values. Use DXL to recreate the tree.

Use **导出含图 ZIP** for DOCX embedded PNG/JPEG and PDF bitmap images. Extract the complete ZIP and run import.dxl in an empty module. If prompted, paste the full path to the folder containing import.dxl and click Continue. Review OLE embedding results in the DOORS client.

### Run or build from source

With Python 3.10+, run `setup.bat` to install dependencies, `run.bat` to launch, `python -m unittest -v` to test, or `build.bat` to generate `dist/DOORS-Importer.exe`. The application works offline after installation.
