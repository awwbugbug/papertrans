# PaperTrans 换机交接

更新时间：2026-08-03

这份文件用于在另一台 Windows 电脑上继续开发。不要依赖原聊天记录；打开仓库后，先按
“阅读顺序”恢复上下文，再按“新电脑恢复”重建环境。

## 1. 阅读顺序

1. `AGENTS.md`
2. `HANDOFF.md`
3. `README.md`
4. `docs/BUILD_FLOW.md`
5. `frontend/AGENTS.md`（修改桌面界面时）

当前 Git 分支是 `codex/m7-desktop-client`。本文件与当前代码会一起提交为迁移快照；解压后
运行 `git log -1 --oneline` 即可确认快照提交。

## 2. 项目目标与架构边界

PaperTrans 是保留学术论文 PDF 排版的中文翻译工具。当前稳定流水线覆盖原生文本提取、
阅读顺序恢复、受保护内容、可插拔翻译 provider、布局修复、PDF 重绘、质量门以及可选的
PP-OCRv6 OCR。

- `domain/`：与 provider 无关的文档模型。
- `ingest/`：输入文件到 Document IR。
- `translation/`：provider 接口及适配器。
- `layout/`：译文测量与排版求解。
- `render/`：输出 PDF。
- `inspect/`：可检查诊断产物。
- `qa/`：自动质量指标和回归门。
- `src/papertrans/desktop/`：本地 FastAPI 服务、任务执行和 Tauri 启动器。
- `frontend/`：React 19 + TypeScript + Vite + Tauri 2 桌面客户端。

翻译 provider 不得接触 PDF 渲染逻辑；渲染器不得调用外部翻译 API。API 密钥只能存在于
当前进程或前端会话内，不能写入 Git、缓存身份、任务产物、诊断或测试夹具。

## 3. 当前完成状态

### PDF 翻译流水线

- M0-M3、M4.1-M4.3、M5.1、M5-C、M6.1-M6.4 已完成。
- `mock` 是默认离线 provider；DeepSeek、Kimi 和 OpenAI-compatible 接口由用户显式选择，
  失败时不得自动切换 provider。
- 引用、URL、DOI、变量和单位在 provider 调用前受到占位符保护。
- 正常译文、紧凑译文、受控字体回退、跨区域流和独立布局验证已经接入。
- OCR 为显式开启项；混合页面只对足够大的图片区域进行 PP-OCRv6 仲裁，不覆盖可靠的
  原生正文。
- 四篇真实论文正常长度基线和 Fast R-CNN 1.3x 长文本场景通过现有质量门。

### Windows 桌面客户端

- M7.1 已从 pywebview/WinForms 迁移到 Tauri 2。
- Tauri 负责无边框窗口、原生边缘缩放、拖动、最大化/还原、文件及目录选择。
- Python FastAPI 子进程使用随机本地端口和会话令牌；所有 `/api/` 请求都需要令牌。
- PDF 拖入、provider/模型配置、会话内 API 密钥、OCR 开关、输出目录、进度和源/译 PDF
  预览均接到真实任务参数。
- 工作区保持五个可调区域：左侧文本原文、源 PDF、翻译设置；右侧文本译文、译文 PDF。
  分隔条支持拖拽、键盘调整以及折叠/恢复。
- 当前视觉基线是 `frontend_tamplate/stitch_papertrans_ui_1/screen.png` 的 Academic Precision
  风格：中性纸面、深靛蓝、细描边、低圆角、紧凑密度。不要恢复大圆角、玻璃效果或环境
  渐变。
- 最终视觉检查见 `design-qa.md`，对照图位于 `artifacts/design-qa/`。

## 4. 尚未完成与推荐下一步

当前不要重做已经稳定的 PDF 流水线。下一阶段按以下顺序推进：

1. 完成 M7.1 在新电脑显示缩放配置下的窗口手感复验：边缘缩放、拖动、拖动还原、双击
   最大化、Windows 11 圆角、文件/目录选择和关闭时子进程退出。
2. M7.2：复用现有 provider、保护层和缓存实现同窗口文本翻译。
3. M7.2：建立本地仓库/任务记录与恢复机制。
4. M7.3：引入 PDF.js 段落级双栏联动、段落选择、选词及对应内容高亮。
5. 后续再做 Python sidecar 打包、安装包、DOCX 导出，以及专用表格/公式识别。

当前“文本译文”和“仓库”主要是界面骨架；文本输入尚未调用 provider，仓库也尚未持久化。
不要把它们误判为已经完成。

## 5. U 盘中必须保留的本地资料

以下目录受 `.gitignore` 管理，不在 Git 快照中，但换机时需要按用途复制：

- `models/paddleocr/PP-OCRv6_medium_det_infer/`
- `models/paddleocr/PP-OCRv6_medium_rec_infer/`
- `test_pdf/`：四篇回归论文。
- `frontend_tamplate/`：用户提供的两套 Stitch 视觉参考，保持未跟踪且不要改写。
- `.papertrans/`：可选；包含历史任务、缓存和输出 PDF。需要保留历史结果时再复制。

务必连同隐藏目录 `.git/` 一起复制，否则会丢失分支和提交历史。建议使用能明确包含隐藏
文件的压缩工具检查压缩包内容。

以下内容不要迁移，应在新电脑重新生成：

- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/src-tauri/target/`
- `.pytest_cache/`、`.ruff_cache/`、`tmp/` 和其他缓存

### 本次 E 盘精简包

2026-08-03 的换机包使用以下约定：

- 压缩包：`E:\PaperTrans-transfer-20260803.zip`
- 独立交接副本：`E:\PaperTrans-HANDOFF.md`
- 压缩包内只有一个根目录 `clean_translate_for_pdf/`。
- 已包含 `.git/`、全部已提交源码、`models/`、`test_pdf/` 和 `frontend_tamplate/`。
- 未包含 `.papertrans/`；历史任务和输出 PDF 如需保留，应另行复制。
- 未包含 `.venv/`、`frontend/node_modules/`、`frontend/dist/`、
  `frontend/src-tauri/target/`、`tmp/`、`.worktrees/` 和测试/代码检查缓存。
- 未包含任何可用 API 密钥。

新电脑上不要直接在 U 盘内运行项目。先把压缩包解压到本机 NTFS 磁盘的短路径，例如
`D:\project_for_codex\clean_translate_for_pdf`，然后执行 `git status --short`；迁移快照应当是
干净工作区。再按照下一节重建依赖。

## 6. 新电脑环境恢复

已验证的旧电脑环境为：Python 3.11.9、Node.js 24.18.0、pnpm 11.9.0、Rust
1.97.1 stable-msvc。项目要求 Python 3.11 或更新版本；Node 和 Rust 可以使用兼容的稳定版。

Windows 还需要：

- Visual Studio Build Tools 2022，并勾选“使用 C++ 的桌面开发”和 Windows SDK。
- Rust stable-msvc 工具链。
- Microsoft Edge WebView2 Runtime。
- Node.js 和 pnpm。

在项目根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev,desktop]"

cd .\frontend
pnpm install --frozen-lockfile
cd ..
```

如需运行本地 OCR，再安装 OCR 依赖；模型文件仍使用上节列出的本地目录：

```powershell
.\.venv\Scripts\python -m pip install -e ".[ocr]"
```

## 7. 启动与验证

启动 Tauri 桌面客户端：

```powershell
.\.venv\Scripts\papertrans-desktop
```

该启动器会寻找 Visual Studio C++ 环境并将 `%USERPROFILE%\.cargo\bin` 临时加入 PATH。
仅调试网页界面时可执行：

```powershell
cd .\frontend
pnpm dev
```

提交前的基础验证：

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .

cd .\frontend
pnpm typecheck
pnpm test:sites
pnpm build
```

本迁移快照的最近验证结果：Python 197 项测试通过，Ruff 通过，TypeScript typecheck 通过，
Sites worker 4 项测试通过，生产构建通过，Tauri Rust 的 `cargo fmt --check` 和 `cargo check`
也通过。换机后仍应在新的 MSVC 环境中重新运行这些检查。

## 8. 密钥与本地配置

Git 中没有可用 API 密钥。换机后按需在当前终端设置，不要写入脚本或文档：

- DeepSeek：`DEEPSEEK_API_KEY`
- Kimi：`MOONSHOT_API_KEY`
- Compatible：`PAPERTRANS_COMPATIBLE_API_KEY`，并在界面中显式填写绝对 HTTP(S) base URL
  和模型名。

桌面界面中的密钥只在当前会话保存，关闭后不会持久化。默认使用 `Mock 版式测试`，无需
密钥即可验证完整 PDF 链路。

## 9. 新电脑交给 Codex 的第一条消息

> 请先完整阅读 AGENTS.md、HANDOFF.md、README.md 和 docs/BUILD_FLOW.md，检查当前分支、
> 最近提交及 git status，不要修改 frontend_tamplate。随后重建依赖并运行 HANDOFF.md 中的
> 验证命令；确认桌面窗口在本机正常后，再继续 M7.2。
