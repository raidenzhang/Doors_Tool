# DOORS Requirement Importer：项目背景

来源：2026-11-25 的 ChatGPT 对话“DOORS需求导入工具”和工作区页面“V0.1 开发需求与 Codex 指令”。以下为需求记录，实际样本和环境尚待验证。

## 目标与约束
- 面向公司 Windows 11，完全本地离线运行，不上传文档、不调用外部 API。
- 将 PDF 中的需求批量整理并导入 DOORS Classic 9.7.2.11。PDF 原文无需求编号，需求可能跨多行，母子层级可能以缩进区分，需用样本确认。
- 最终 Release 为单个 EXE，目标电脑无需安装 Python；在干净的 Windows 11 环境验证。

## V0.1 方案
- 计划使用 Python 3.10+、PyMuPDF 和 Tkinter。按文字坐标、垂直间距合并多行，按横坐标缩进识别多级层级；阈值可调，保持原文顺序，标记不确定层级。
- GUI 支持文件选择，逐条检查原文、分类结果、母子关系、层级、来源页和不确定标记；提供树状预览、手动合并、拆分和调整层级，确认后导出。
- 导出 CSV：Temporary ID、Parent ID、Level、Object Text、Source Page。生成 DXL 脚本依据父子关系创建 DOORS Object；普通 CSV 导入不会自动建立层级。仅向测试 Module 导入，不覆盖或删除已有需求。
- 计划交付 main.py、pdf_parser.py、hierarchy.py、exporter.py、import_requirements.dxl、requirements.txt、setup.bat、run.bat、README.md、build.bat；建议使用 PyInstaller 打包依赖及 DXL 模板。

## 状态和待验证事项
- 原记录表明尚未开发或测试；使用脱敏 PDF 样本验证拆分和缩进，在 DOORS 测试 Module 验证 DXL，使用模拟数据测试中英文、段落和层级。
- 暂不做 Word、OCR、AI 语义识别和 Traceability Link。
- 原始需求页面：https://chatgpt.com/space/page_059820c33b108191aa93bb3268584ecd
