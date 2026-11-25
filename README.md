# DOORS Requirement Importer V0.2

作者 / Author: Raiden.Zhang

## 中文

这是面向 DOORS Classic 9.7.2.11 的需求整理原型，支持离线读取含可选文字的 PDF 和 Word `.docx`，检查并调整文字及层级，再导出 CSV 或 DXL。图表、图片和扫描件 OCR 暂不支持。

### 使用发布版

从 GitHub Release 下载 `DOORS-Importer.exe`，在 Windows 上双击运行。EXE 已打包 Python 和运行依赖，目标电脑无需安装 Python、Word 或额外 Python 包。单文件程序运行时会将组件临时解压到系统临时目录；独立运行仍须在干净的 Windows 11 电脑上验证。

选择 PDF 或 DOCX，调整阈值并解析；检查每条需求，可以编辑、保存、调整层级、合并或按换行拆分。Word 以段落为单位，表格内文字提取为段落，来源记录段落序号而非页码。旧版 `.doc` 请先另存为 `.docx`。复杂样式、编号、文本框、页眉页脚及跨页内容可能需要人工处理。

CSV 为 UTF-8 BOM 格式。可通过 DOORS 的 File > Import > Spreadsheet 导入；Parent ID 和 Level 只是属性，不会自动建立层级。编码、中文及换行需在实际环境验证。

“导出 DXL”生成按确认的层级创建对象的脚本。在 DOORS 打开空的测试 Module，选择 Tools > Edit DXL 加载运行，检查后手动保存。脚本拒绝非空模块。DXL 尚未在 DOORS 9.7.2.11 实测；脚本使用导出电脑的 Windows ANSI 代码页，目标电脑代码页不同时可能乱码。先用少量脱敏需求验证中文、换行和层级。

### 从源码开发和构建

只有开发者需要安装 Python 3.10+ 和依赖：运行 `setup.bat` 安装、`run.bat` 启动、`build.bat` 使用 PyInstaller 生成单文件 EXE。安装依赖需要网络或预先准备的离线包；应用运行时不联网。

## English

This prototype prepares requirements for DOORS Classic 9.7.2.11. It reads text-based PDF and Word `.docx` files offline, allows review and adjustment of text and hierarchy, and exports CSV or DXL. Images, charts, and OCR for scanned documents are not supported yet.

### Using the release

Download `DOORS-Importer.exe` from GitHub Releases and run it on Windows. Python and application dependencies are bundled; users do not need to install Python, Word, or additional Python packages. The one-file executable extracts components to the system temporary directory at runtime. Standalone operation still needs verification on a clean Windows 11 computer.

Select PDFs or DOCX files, adjust the thresholds, and parse them. Review each requirement; edit and save text, change levels, merge entries, or split at line breaks. Word content is split by paragraph, including text within tables. Sources show paragraph numbers rather than pages. Convert legacy `.doc` files to `.docx` first. Complex styles, numbering, text boxes, headers, footers, and content spanning pages may require manual correction.

CSV is UTF-8 with BOM. Import it using DOORS File > Import > Spreadsheet. Parent ID and Level are ordinary attributes and do not automatically create a hierarchy. Verify encoding, Chinese text, and line breaks in the target environment.

Export DXL to generate a script that creates the reviewed hierarchy. Open an empty test module in DOORS, load and run the script via Tools > Edit DXL, review the result, and save manually. The script rejects non-empty modules. It has not yet been tested in DOORS 9.7.2.11. The script uses the exporting computer's Windows ANSI code page; a different target code page may corrupt text. First verify Chinese text, line breaks, and hierarchy with a small anonymized sample.

### Developing and building from source

Only developers need Python 3.10+ and dependencies: run `setup.bat` to install, `run.bat` to launch, and `build.bat` to package the single EXE with PyInstaller. Dependency installation requires network access or pre-arranged offline packages; the application itself does not use the network at runtime.
