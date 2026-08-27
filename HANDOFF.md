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

翻译 provider 不得接触 PDF 渲染逻辑；渲染器不得调用外部翻译 API。桌面 API 配置仅由
Tauri 写入当前 Windows 用户的凭据管理器，运行时载入前端内存；不能写入 Git、浏览器
存储、缓存身份、Python 任务产物、诊断或测试夹具。

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
- PDF 拖入、provider/模型配置、Windows 凭据管理器中的 API 密钥、OCR 开关、输出目录、进度和源/译 PDF
  预览均接到真实任务参数。
- 工作区保持五个可调区域：左侧文本原文、源 PDF、翻译设置；右侧文本译文、译文 PDF。
  分隔条支持拖拽、键盘调整以及折叠/恢复。
- 当前视觉基线是 `frontend_tamplate/stitch_papertrans_ui_1/screen.png` 的 Academic Precision
  风格：中性纸面、深靛蓝、细描边、低圆角、紧凑密度。不要恢复大圆角、玻璃效果或环境
  渐变。
- 最终视觉检查见 `design-qa.md`，对照图位于 `artifacts/design-qa/`。

## 4. 尚未完成与推荐下一步

当前不要重做已经稳定的 PDF 流水线。下一阶段按以下顺序推进：

1. M7.1 窗口手感复验已在 2026-08-25 通过：边缘缩放、拖动、拖动还原、最大化、
   Windows 圆角和无黑边外观均符合预期。
2. M7.2：文本翻译前后端闭环已经完成，现有面板支持按钮/Ctrl+Enter提交以及加载、成功、
   失败和旧结果清理状态。
3. M7.2：本地仓库/任务记录与文本恢复已经实现并通过用户验收。
4. M7.3：PDF.js 单页阅读、可选择文字层、段落几何映射、双击联动、选区翻译和稳定无闪烁重绘已经实现，并通过用户验收。
5. M7.4：有界虚拟页面窗口、当前页观察、逐页映射缓存和双栏连续翻页同步均已实现并通过桌面真实交互验收，里程碑已关闭。
6. M7.5 前三项已经通过用户验收：导航切换保留翻译工作区、API 配置按 provider 安全持久化、仓库显示有界论文标题/文本摘要。禁止改回条件卸载、`display: none`、跨 provider 共用密钥，或把密钥写入浏览器/Python 持久化。
7. M7.5 第四项已通过用户验收：仓库支持确认删除；PDF 历史删除保留原文和输出，文本历史删除原子移除应用内部任务目录；设置页可分别清理翻译缓存和无引用临时导入副本。运行任务期间禁止删除对应任务和清理缓存，任何递归清理不得越过应用托管根目录或跟随链接。
8. 关闭生命周期已并入第四项：默认点击“×”隐藏到 Tauri 系统托盘并保留当前工作区/后端，单击托盘或菜单可恢复；托盘明确退出或设置中开启“关闭主窗口时退出应用”才真正退出并清理后端。
9. `0.1.1` 已冻结并完成 PyInstaller sidecar 与 NSIS 安装包。运行 `.\scripts\build_windows_release.ps1` 可执行完整测试、sidecar API 冒烟检查和安装包构建；安装态数据位于 `%LOCALAPPDATA%\com.papertrans.desktop`。Windows 主程序使用 GUI 子系统，所有安装与桌面入口共享品牌图标，sidecar 进程树受 kill-on-close Job Object 约束。安装包不含 OCR 模型、历史任务、API Key、测试 PDF 或开发缓存。DOCX 导出以及专用表格/公式识别继续延期。

当前“文本译文”调用真实后端 provider 路径；“仓库”通过 `.papertrans/library/` 保存任务。
`library.json` 不含文本正文和 API Key；文本正文与译文位于独立本地任务目录，用于重启恢复。
M7.2 已关闭；不要跳过 PDF.js 文字层和几何映射，直接用字符串模糊匹配实现段落联动。

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
也通过。换机后仍应在新的 MSVC 环境中重新运行这些检查。Windows 启动器会从当前 Visual Studio 安装中解析 x64 `link.exe`，并显式设置 Cargo 的 MSVC 链接器，避免 Git/Hermes 的同名工具抢占构建。

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
