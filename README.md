# PaperTrans

PaperTrans 是一个面向学术论文的保版式 PDF 翻译项目。项目目标不是简单地提取文字并覆盖回 PDF，而是建立可检查的文档中间表示，恢复阅读顺序，并在可读性约束下尽量保持原页面结构。

当前版本已完成 **M5.1 版式安全验证与有限局部修复基线**：现有 CJK 排版会依次尝试普通译文、紧凑译文和受控字号回退，再由独立验证器复查完整性、页边界、字号及碰撞；不安全结果进入 REVIEW，且不会创建或覆盖输出 PDF。M4.3 的 DeepSeek、Kimi 和自定义 OpenAI-compatible 接入保持不变。`mock` 仍是默认提供方且完全离线；模拟中文只用于检验管线和排版，不代表真实翻译质量。

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
- 在渲染前独立复验布局；只有临时 PDF 通过全部质量门后才原子替换正式输出。
- REVIEW 任务保留诊断、译文和缓存，但不创建或覆盖可能不安全的 `output.pdf`。
- 输出 `protected-segments.json`，记录稳定占位符、保护类型、原值和恢复验证结果。
- 对占位符缺失、重复及未知标记执行失败保护；验证未通过的译文不会进入 PDF 排版。
- 翻译结果按提供方配置指纹和请求内容缓存；不同模型、提示词版本或 Mock 长度配置不会错误共享缓存。
- 每个成功段落立即原子落盘，任务中途失败后可以从已完成段落继续。
- 输出 `provider-run.json`，记录缓存命中、真实调用、重试、失败及限速等待统计。
- 支持显式选择 `deepseek`、`kimi` 和 best-effort 的 `compatible` 提供方；一次 JSON 响应同时返回普通译文与紧凑译文。
- 对 DeepSeek/Kimi 的新调用记录输入、缓存输入、输出令牌和按日期快照估算的费用；本地缓存命中不重复计费。

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

### 外部翻译提供方

外部提供方必须显式选择。密钥只从环境变量读取，没有也不应增加 API-key 命令行参数。DeepSeek 默认模型为 `deepseek-v4-flash`，Kimi 默认模型为 `kimi-k2.6`；两者默认关闭 thinking 模式，也可以用 `--model` 覆盖模型名。

```powershell
$env:DEEPSEEK_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider deepseek

$env:MOONSHOT_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider kimi

$env:MY_PROVIDER_API_KEY = "set-locally"
.\.venv\Scripts\papertrans translate .\paper.pdf --provider compatible `
  --base-url https://example.com/v1 `
  --model example-model `
  --api-key-env MY_PROVIDER_API_KEY
```

`compatible` 只保证尽力适配支持 Chat Completions 和 JSON object 响应的服务，必须提供绝对 HTTP(S) `--base-url` 和 `--model`；不同服务的私有字段、鉴权方式或响应差异可能仍需专用适配器。PaperTrans 不会在提供方失败时自动切换到其他服务，以免在未授权的情况下把论文发送到另一端点。

选择外部提供方后，PaperTrans 会逐段发送经过占位符保护的论文文本以及必要的段落上下文；不会上传整份 PDF。这里的“保护”用于确保引用、URL、DOI、变量和单位可恢复，并不等于隐私脱敏。处理未公开或敏感论文前，应先确认所选服务的隐私与数据保留条款。API 密钥不会进入缓存身份、任务 JSON 或错误摘要。

费用只是按提供方公开单价计算的日期快照估算，并非账单。当前快照日期为 **2026-07-31**：DeepSeek 以 USD 估算，缓存输入/未缓存输入/输出分别为 `$0.0028 / $0.14 / $0.28` 每百万令牌；Kimi 以 CNY 估算，分别为 `¥1.10 / ¥6.50 / ¥27.00` 每百万令牌。服务方后续调价不会自动改写历史任务。

可选的真实服务 smoke test 只应使用一份短小、合成且不敏感的 PDF：先在当前本地终端设置新的环境变量密钥，再显式选择提供方，并使用独立输出目录。确认 `provider-run.json`、保护验证和质量门后，立即在服务方控制台撤销临时密钥。不要把真实密钥写入命令历史、脚本、仓库或 bug 报告；自动化测试始终使用 `MockTransport`，不会访问真实网络。

翻译产物包括 `output.pdf`、`document.json`、`protected-segments.json`、`provider-run.json`、`translations.json`、`layout.json` 和 `translation-report.json`。保护映射和提供方运行状态都会在请求前落盘；成功后分别更新为 `validated` 和 `completed`。默认使用本机 Microsoft YaHei；可通过 `PAPERTRANS_CJK_FONT` 和 `PAPERTRANS_CJK_BOLD_FONT` 指定本地字体文件。字体仅在运行时读取，不会复制进仓库。

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
