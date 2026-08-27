# PaperTrans

PaperTrans 是一个面向学术论文的保版式 PDF 翻译项目。项目目标不是简单地提取文字并覆盖回 PDF，而是建立可检查的文档中间表示，恢复阅读顺序，并在可读性约束下尽量保持原页面结构。

当前版本已经完成 **M7.5 桌面产品稳定化**并通过用户验收。`0.1.1` 冻结修正版使用 React/Tauri 2 桌面壳和自包含 Python sidecar，通过受会话令牌保护的随机本地端口接入既有 PDF/文本翻译路径；Windows NSIS 安装包已经可复现构建。

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
- 每个段落请求最多携带 200 字符章节标题及前后各 600 字符相邻文本，不会把整份 PDF 作为单次请求上传。
- 支持 `--glossary` JSON 术语表；只发送当前段命中的术语，语境与术语变化会自动隔离缓存。
- `inspect` 输出 `ocr-plan.json`，按页记录原生字符量、文本质量、栅格图覆盖率、矢量对象数量、决策及置信度。
- OCR 决策分为 `keep_native`、`run_ocr`、`use_ocr`、`review` 和 `skip_blank`，并直接标注在 layout overlay 右上角。
- 未启用 OCR 时，`run_ocr` 或 `review` 页面会在 provider 调用前阻止翻译；启用后只有通过字符量与平均置信度门槛的页面进入 `use_ocr`。
- 原生文字区域和 TextFlow 在 Document IR 中保留 `content_source` 与 `content_confidence` 来源信息。
- `ocr-run.json` 记录调用页数、接受/拒绝行数和设备类型，不记录论文正文或模型绝对路径。
- OCR 行合并边以 `ocr_same_paragraph` 写入 TextFlow 诊断；跨页宽编号 `0` 和栏编号 `1/2` 均被覆盖。
- `inspect --ocr-reference <pdf>` 可输出 `ocr-quality.json`，记录 CER、词序相似度和字符覆盖率，不保存参考或识别正文。
- 提供 Windows 桌面入口；无边框窗口保留标准的边缘缩放、最大化/还原、拖拽还原和 Windows 圆角，本地随机端口使用会话令牌保护。
- PDF 与文本翻译已合并为同一可调工作区：左侧依次放置文本原文、原 PDF 与翻译设置，右侧放置文本译文与译文 PDF；各纵向区域可拖拽并折叠为长条。PDF 与文本翻译均已接入真实任务路径，仓库按 PDF/文本双栏展示，并可恢复已完成 PDF 到双栏阅读器。左右 PDF.js 阅读器可在设置中独立控制翻页同步和缩放同步；按住空格可直接拖动画布视口。
- 仓库 PDF 任务显示从论文首页提取并规范化的论文标题，旧的文件名记录会自动补齐；文本任务显示最多 120 字符的原文摘要。两类内容都在单行内省略显示，文本完整内容仍只保存在对应的本地任务文件中，不复制进仓库索引。
- 仓库任务支持经确认后删除。删除 PDF 历史只移除仓库记录，保留原始论文和已生成译文；删除文本历史会同步移除 `.papertrans/library/<task-id>/` 中由应用管理的原文与译文副本。运行中的任务禁止删除。
- 设置页显示翻译缓存与临时导入副本的文件数和占用，可分别确认清理；缓存清理不会触碰任务、原始论文或生成译文，临时清理只删除没有被当前阅读器、运行任务或仓库引用的 `.papertrans/jobs/uploads/` 副本。翻译运行期间禁止清理缓存。
- 默认点击主窗口“×”只隐藏到 Windows 系统托盘，本地后端与当前阅读状态继续保留；单击托盘图标或选择“显示 PaperTrans”可恢复窗口，托盘菜单“退出 PaperTrans”会真正退出并清理后端。设置页可开启“关闭主窗口时退出应用”，该非敏感偏好仅保存在当前用户的浏览器本地存储中。
- 已完成 M7.3 段落联动的后端几何基础：受会话令牌保护的逐页阅读映射接口返回稳定 TextFlow ID、原文与实际排版采用的译文，以及原文区域框和译文行框；响应不暴露任务路径、字体路径或密钥。
- 前端在 PDF.js 画布上叠加透明可选择文字层，并按已完成任务的当前页读取 `m7_reading_map_v1`；稳定段落框已经缩放到两侧页面表面，默认不可见，只有当前选中 flow 会显示且不会拦截文字选择。
- PDF.js 重绘与普通 React 交互状态解耦；分栏或窗口连续缩放会在尺寸稳定后后台渲染，并只在完整画布与文字层就绪后原子替换可见页面，避免拖拽、选词和定位造成闪白。
- PDF.js 阅读器已经使用连续页面栈：整篇论文只保留轻量页面占位，当前页前后各 2 页才挂载画布与文字层（最多 5 个页面表面）；视口占比最大的页面更新工具栏页码，按钮跳页不会与滚动观察器形成反馈循环，远页卸载时释放页面资源。
- 跨页段落定位使用页面在连续滚动栈内的真实坐标，并在“跳到目标页—加载映射—段落居中”的完整过程持有程序化导航锁，避免中途页码观察事件清除高亮。Ctrl+滚轮先对现有页面做以鼠标为锚点的轻量缩放预览，停止输入后才执行一次高清原子重绘，不再让每个滚轮事件重启所有相邻页面。
- 已完成有界逐页阅读映射缓存：左右阅读器共享当前任务的会话内缓存，加载范围是两侧当前页各自前后 2 页的并集（最多 10 页）；每页完成后立即可交互，快速滚动会取消过期请求，远页和任务切换会移除缓存，映射正文不进入浏览器持久化。
- 连续翻页同步只广播稳定页码：视口占比最大的页面保持 80ms 后才更新工具栏并在同步开启时驱动另一侧；边界抖动会替换未提交候选，程序化跳页会取消候选并阻止反馈。关闭同步时两侧继续独立滚动，显式双击映射仍可跨页定位。
- 翻译工作区不会因切换到仓库或设置而卸载；离开时只以 `visibility` 和 `inert` 隐藏并隔离交互，不使用会让 PDF.js 容器尺寸归零的 `display: none`。返回翻译页时复用原 PDF 文档、Canvas、逐页映射缓存和阅读器滚动位置。
- 设置页的 DeepSeek、Kimi 和兼容接口均可打开统一配置窗口；API Key、模型和兼容接口地址按 provider 隔离，并由 Tauri 保存到当前 Windows 用户的凭据管理器。保存配置不会发起测试请求，密钥不会写入浏览器存储、任务记录、诊断或缓存。
- 段落双击通过 PDF 坐标命中而不是覆盖透明按钮，单击和拖选不会触发定位；选中的稳定 flow ID 同时驱动左右几何高亮。即使关闭翻页同步，主动双击映射仍会将另一侧跳到该 flow 对应页面。
- 联动状态记录点击来源，只允许另一侧自动滚动；目标已经完整可见时保持静止，否则在水平和垂直方向居中，并遵循系统“减少动画”设置。
- 在单个映射段落内框选单词或短语时，文字选择与段落定位互斥，不会同时触发双栏跳转；系统不会伪造单词级双语对齐。该选择不持久化，也不会自动调用翻译 API。
- 已完成显式“翻译所选”闭环：原文 PDF 的有效同段选区旁会显示主动触发按钮，加载、失败和译文在选区附近的页内浮层呈现，不占用工具栏且不挤压阅读区。接口单次最多 300 字符，复用 provider、占位符保护、重试、费用统计与可靠缓存，但使用独立提示词/缓存上下文且不创建仓库记录。

## 本地开发

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

### 运行桌面客户端

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev,desktop]"
cd .\frontend
pnpm install
cd ..
.\.venv\Scripts\papertrans-desktop
```

Tauri 开发构建需要 Rust stable-msvc、Microsoft C++ Build Tools（勾选“使用 C++ 的桌面开发”）和 WebView2。`papertrans-desktop` 会自动载入已安装的 Visual Studio C++ 开发环境、显式选择其中的 x64 MSVC 链接器，再启动 Tauri；这可避免 Git/Hermes 自带的同名 `link.exe` 抢占构建。桌面外壳随后启动 Python FastAPI 子进程，并为每次运行生成随机本地端口与会话令牌。默认选择 `Mock 版式测试`，无需 API 密钥即可验证完整 PDF 链路；DeepSeek、Kimi 和兼容接口必须由用户显式选择。桌面配置由 Windows 凭据管理器长期保存，启动时载入当前会话；密钥不会进入浏览器存储或 Python 任务产物。

### 构建 Windows 安装包

```powershell
.\scripts\build_windows_release.ps1
```

脚本会依次运行 Python、Ruff、前端与 Rust 验收，使用 PyInstaller 构建自包含 sidecar，执行本地 API 冒烟测试，再生成 `frontend/src-tauri/target/release/bundle/nsis/PaperTrans_0.1.1_x64-setup.exe` 和 SHA256。标准安装包会携带本机 `models/paddleocr/` 下经过构建前完整性检查的 PP-OCRv6 medium 检测与识别权重，安装后由 sidecar 直接读取只读资源目录；它不包含 `.papertrans/`、历史任务、API Key、测试 PDF 或开发缓存。安装态数据写入 `%LOCALAPPDATA%\com.papertrans.desktop`。当前安装包未做代码签名，Windows 可能显示 SmartScreen 提示。

全局品牌图标保存在 `assets/branding/papertrans-icon.svg`，同时保留忠实呈现选定稿渐变与抗锯齿的 `papertrans-icon.png`。发布脚本会重新生成两份品牌母版，并由 PNG 主稿统一导出窗口、任务栏、系统托盘、桌面快捷方式和安装程序使用的 ICO/PNG 资源，避免矢量追踪误差或各入口出现不同版本。

检查一份 PDF：

```powershell
.\.venv\Scripts\papertrans inspect .\paper.pdf
```

检查产物中的 `ocr-plan.json` 会列出逐页 OCR 决策。默认不执行 OCR；使用已经解压到本地的模型时需显式开启：

```powershell
.\.venv\Scripts\papertrans inspect .\paper.pdf `
  --ocr-backend paddleocr `
  --ocr-model-dir .\models\paddleocr `
  --ocr-device cpu
```

同样的 OCR 参数可用于 `translate`。CPU 是当前可复现基线；程序不会自动下载模型，且会自动兼容识别模型目录多嵌套一层的情况。

对页数和尺寸一致、带可靠文字层的参考 PDF 计算 OCR 质量：

```powershell
.\.venv\Scripts\papertrans inspect .\scan.pdf `
  --ocr-backend paddleocr `
  --ocr-model-dir .\models\paddleocr `
  --ocr-reference .\reference.pdf `
  --output-dir .\.papertrans\ocr-quality
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

使用可选术语表：

```json
{
  "region proposal": "候选区域",
  "intersection over union": "交并比"
}
```

```powershell
.\.venv\Scripts\papertrans translate .\paper.pdf --provider deepseek --glossary .\glossary.json
```

术语表必须是 UTF-8 JSON 对象，最多 500 项；路径和完整术语内容不会写入任务报告。

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

翻译产物包括 `output.pdf`、`document.json`、`ocr-plan.json`、`ocr-run.json`、`protected-segments.json`、`provider-run.json`、`translations.json`、`layout.json` 和 `translation-report.json`。OCR 预检与可选本地识别在 provider 调用前完成；保护映射和提供方运行状态也会在请求前落盘。默认使用本机 Microsoft YaHei；可通过 `PAPERTRANS_CJK_FONT` 和 `PAPERTRANS_CJK_BOLD_FONT` 指定本地字体文件。字体仅在运行时读取，不会复制进仓库。

当前渲染仍使用白色填充清除原文字形，因此只适合白底论文；彩色背景、纹理背景及与文本重叠的复杂矢量对象尚未解决。

输出内容：

```text
.papertrans/demo/
├── document.json
├── text-flows.json
├── ocr-plan.json
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
