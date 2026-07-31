# PaperTrans

PaperTrans 是一个面向学术论文的保版式 PDF 翻译项目。项目目标不是简单地提取文字并覆盖回 PDF，而是建立可检查的文档中间表示，恢复阅读顺序，并在可读性约束下尽量保持原页面结构。

当前版本已完成 **M4.2 翻译可靠性层基线**：除占位符保护外，所有翻译提供方都可以通过统一包装器获得原子磁盘缓存、指数退避重试、请求限速和逐段断点恢复。模拟中文只用于检验管线和排版，不代表真实翻译质量。

## 当前能力

- 从文本型 PDF 提取页面、文本块、图片块、坐标和基础字体信息。
- 输出统一的 `document.json` 文档中间表示。
- 生成原始页面 PNG 和带区域标记的布局预览图。
- 生成 Markdown 检查报告。
- 恢复基础双栏阅读顺序，并建立可追溯的段落级 `TextFlow`。
- 记录跨栏、跨页和断词修复决策及其置信度。
- 默认保护公式、图内文字、表内文字和参考文献。
- 支持零翻译回环，按原始span基线、字号、颜色和字体类别重新绘制英文。
- 自动检查页数、页面尺寸、链接、文本相似度和视觉差异。
- 提供不调用外部 API 的伪中文翻译器和 `translate --provider mock` 命令。
- 支持中文标点禁则、同一 TextFlow 跨原始区域流动、紧凑译文候选和可控字号回退。
- 使用页面级占用检测避免译文之间及译文与公式、图表等受保护区域发生碰撞。
- 对溢出、文字碰撞、新增低于 6pt 的文字、最小字号比例、链接及页面几何执行自动质量门禁。
- 输出 `protected-segments.json`，记录稳定占位符、保护类型、原值和恢复验证结果。
- 对占位符缺失、重复及未知标记执行失败保护；验证未通过的译文不会进入 PDF 排版。
- 翻译结果按提供方配置指纹和请求内容缓存；不同模型、提示词版本或 Mock 长度配置不会错误共享缓存。
- 每个成功段落立即原子落盘，任务中途失败后可以从已完成段落继续。
- 输出 `provider-run.json`，记录缓存命中、真实调用、重试、失败及限速等待统计。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

检查一份 PDF：

```powershell
.\.venv\Scripts\papertrans inspect .\paper.pdf
```

指定输出目录：

```powershell
.\.venv\Scripts\papertrans inspect .\paper.pdf --output-dir .\.papertrans\demo
```

执行零翻译回环：

```powershell
.\.venv\Scripts\papertrans roundtrip .\paper.pdf --output-dir .\.papertrans\roundtrip-demo
```

回环产物包括 `output.pdf`、`document.json` 和 `roundtrip-report.json`。当前M2使用白色填充清除原文字形，适合首批白底学术论文；复杂背景将在后续内容流重建阶段处理。

执行本地模拟中文翻译：

```powershell
.\.venv\Scripts\papertrans translate .\paper.pdf --provider mock --output-dir .\.papertrans\mock-demo
```

用加长译文进行版式压力测试：

```powershell
.\.venv\Scripts\papertrans translate .\paper.pdf --provider mock --length-factor 1.3 --output-dir .\.papertrans\mock-demo-1.3
```

指定共享缓存、最大尝试次数和请求速率：

```powershell
.\.venv\Scripts\papertrans translate .\paper.pdf --provider mock --cache-dir .\.papertrans\cache\mock --max-attempts 3 --requests-per-second 2
```

翻译产物包括 `output.pdf`、`document.json`、`protected-segments.json`、`provider-run.json`、`translations.json`、`layout.json` 和 `mock-translation-report.json`。保护映射和提供方运行状态都会在请求前落盘；成功后分别更新为 `validated` 和 `completed`。默认使用本机 Microsoft YaHei；可通过 `PAPERTRANS_CJK_FONT` 和 `PAPERTRANS_CJK_BOLD_FONT` 指定本地字体文件。字体仅在运行时读取，不会复制进仓库。

当前渲染仍使用白色填充清除原文字形，因此只适合白底论文；彩色背景、纹理背景及与文本重叠的复杂矢量对象尚未解决。

输出内容：

```text
.papertrans/demo/
├── document.json
├── text-flows.json
├── inspect-report.md
├── pages/
└── overlays/
```

完整的迭代顺序、质量门槛和模型下载策略见 [构建流程](docs/BUILD_FLOW.md)。

## 项目原则

- 文档结构优先于 OCR。
- 排版质量和内容完整性必须可测量。
- 翻译服务、OCR引擎和PDF渲染器保持可替换。
- 第一阶段先支持文本型学术论文，再增加扫描件。
- 大模型和OCR模型不自动下载；需要时先提供官方地址和目标路径。
