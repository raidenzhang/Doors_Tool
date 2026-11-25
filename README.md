# DOORS 需求整理工具 V0.1

Windows 11 离线运行。开发环境安装 Python 3.10+，运行 setup.bat 安装依赖，然后运行 run.bat。运行 build.bat 可在 dist 目录生成单个 EXE；目标电脑无需 Python。安装依赖时需要网络或预先准备好的离线包，应用运行时不联网。

选择一个或多个可选中文字的 PDF 或 Word .docx，设置行距与缩进阈值后解析。Word 按段落切分，包含表格内段落；依据段落直接缩进和列表级别推测层级，来源记录段落序号而非页码（DOCX 无固定页码）。复杂样式继承、自动编号显示、文本框及图片内容可能无法识别。旧版 .doc 请先另存为 .docx。逐条检查并编辑，保存修改；可调整层级、合并或按编辑框内换行拆分。确认后导出 UTF-8 BOM CSV。解析是启发式方法，页眉、页脚、表格和跨页内容可能需要手工处理；暂不支持扫描件 OCR。跨页内容不会自动合并。

CSV 不会自动在 DOORS 中建立层级。可以选择“导出 DXL”生成脚本，在 DOORS 打开的空测试 Module 中选择 Tools > Edit DXL，加载并运行脚本；检查结果后手动保存。脚本将创建对象及层级，不自动保存，非空模块会拒绝执行。重复运行前须检查模块状态。脚本尚未在 DOORS 9.7.2.11 实测，中文使用导出电脑的 Windows ANSI 代码页，目标 DOORS 使用不同代码页时可能乱码；先用小样本验证。实际 PDF、中文和干净 Windows 环境仍需验证。

在 DOORS 测试模块中选择 File > Import > Spreadsheet，选择导出的 CSV，选择使用第一行列名映射属性，并核对 Object Text 映射。Temporary ID、Parent ID、Level 和 Source Page 是普通数据属性，不会自动创建层级。CSV 为 UTF-8 BOM，实际中文、换行与编码兼容性需在目标 DOORS 环境测试。
