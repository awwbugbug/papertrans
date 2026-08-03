import { ChangeEvent, CSSProperties, Dispatch, DragEvent, KeyboardEvent, PointerEvent, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { artifactUrl, loadJob, loadSystemInfo, registerSource, sourceUrl, startJob, uploadPdf } from "./api";
import type { JobState, ProviderName, SourceDocument, SystemInfo } from "./types";

const FALLBACK_SYSTEM: SystemInfo = {
  providers: [
    { name: "deepseek", label: "DeepSeek", defaultModel: "deepseek-v4-flash", requiresApiKey: true },
    { name: "kimi", label: "Kimi", defaultModel: "kimi-k2.6", requiresApiKey: true },
    { name: "compatible", label: "兼容接口", defaultModel: null, requiresApiKey: true },
    { name: "mock", label: "Mock 版式测试", defaultModel: null, requiresApiKey: false },
  ],
  ocr: { ready: false, modelDir: null },
  defaultOutputDir: ".papertrans/jobs",
};

type View = "translate" | "library" | "settings";
type InputMode = "pdf" | "text";
const SETTINGS_COLLAPSE_THRESHOLD = 78;

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>;
}

function Header({ view, onView }: { view: View; onView: (view: View) => void }) {
  return (
    <header
      className="app-header pywebview-drag-region"
      onDoubleClick={(event) => {
        if (event.target === event.currentTarget) window.pywebview?.api?.toggle_maximize_window?.();
      }}
    >
      <button className="brand" onClick={() => onView("translate")}>PaperTrans</button>
      <nav aria-label="主导航">
        {(["library", "translate", "settings"] as const).map((item) => (
          <button
            key={item}
            className={view === item ? "nav-item active" : "nav-item"}
            onClick={() => onView(item)}
          >
            {{ library: "仓库", translate: "翻译", settings: "设置" }[item]}
          </button>
        ))}
      </nav>
      <div className="window-controls" aria-label="窗口控制">
        <button aria-label="最小化" title="最小化" onClick={() => window.pywebview?.api?.minimize_window?.()}><Icon name="remove" size={17} /></button>
        <button aria-label="最大化或还原" title="最大化或还原" onClick={() => window.pywebview?.api?.toggle_maximize_window?.()}><Icon name="crop_square" size={15} /></button>
        <button className="close-window" aria-label="关闭" title="关闭" onClick={() => window.pywebview?.api?.close_window?.()}><Icon name="close" size={18} /></button>
      </div>
    </header>
  );
}

function Segmented({ value, onChange }: { value: InputMode; onChange: (value: InputMode) => void }) {
  return (
    <div className="segmented" aria-label="输入类型">
      <button className={value === "pdf" ? "selected" : ""} onClick={() => onChange("pdf")}>
        <Icon name="picture_as_pdf" size={17} /> PDF 文件
      </button>
      <button className={value === "text" ? "selected" : ""} onClick={() => onChange("text")}>
        <Icon name="text_fields" size={17} /> 文本
      </button>
    </div>
  );
}

function useStoredPercent(key: string, initial: number): [number, Dispatch<SetStateAction<number>>] {
  const [value, setValue] = useState(() => {
    const saved = Number(window.localStorage.getItem(key));
    return Number.isFinite(saved) && saved > 0 ? saved : initial;
  });
  const update: Dispatch<SetStateAction<number>> = (next) => {
    setValue((current) => {
      const resolved = typeof next === "function" ? next(current) : next;
      window.localStorage.setItem(key, String(resolved));
      return resolved;
    });
  };
  return [value, update];
}

function ResizeHandle({ orientation, label, onDrag, onNudge }: {
  orientation: "vertical" | "horizontal";
  label: string;
  onDrag: (delta: number) => void;
  onNudge: (delta: number) => void;
}) {
  const lastCoordinate = useRef<number | null>(null);
  const coordinate = (event: PointerEvent<HTMLDivElement>) => (
    orientation === "vertical" ? event.clientX : event.clientY
  );
  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    lastCoordinate.current = null;
    document.body.classList.remove("is-resizing", `is-resizing-${orientation}`);
  };
  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const backward = orientation === "vertical" ? event.key === "ArrowLeft" : event.key === "ArrowUp";
    const forward = orientation === "vertical" ? event.key === "ArrowRight" : event.key === "ArrowDown";
    if (!backward && !forward) return;
    event.preventDefault();
    onNudge(backward ? -2 : 2);
  };
  return (
    <div
      className={`resize-handle ${orientation}`}
      role="separator"
      aria-label={label}
      aria-orientation={orientation}
      tabIndex={0}
      onKeyDown={handleKey}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        lastCoordinate.current = coordinate(event);
        document.body.classList.add("is-resizing", `is-resizing-${orientation}`);
      }}
      onPointerMove={(event) => {
        if (!event.currentTarget.hasPointerCapture(event.pointerId) || lastCoordinate.current === null) return;
        const nextCoordinate = coordinate(event);
        onDrag(nextCoordinate - lastCoordinate.current);
        lastCoordinate.current = nextCoordinate;
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
    ><span /></div>
  );
}

function UploadCard({ onPick, onDrop }: {
  onPick: () => void;
  onDrop: (file: File) => void;
}) {
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) onDrop(file);
  };
  return (
    <section className="glass-card upload-shell">
      <div
        className="upload-zone"
        onClick={onPick}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => event.key === "Enter" && onPick()}
      >
        <div className="upload-icon"><Icon name="upload_file" size={29} /></div>
        <h2>拖入或点击选择 PDF</h2>
        <p>支持文本型、扫描型和混合型 PDF</p>
      </div>
    </section>
  );
}

function SourcePanel({ source, onPick, onDrop, onClear }: {
  source: SourceDocument;
  onPick: () => void;
  onDrop: (file: File) => void;
  onClear: () => void;
}) {
  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) onDrop(file);
  };
  return (
    <section
      className="glass-card source-panel"
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
    >
      <div className="document-toolbar">
        <div className="document-identity">
          <span className="document-kind"><Icon name="picture_as_pdf" size={17} /></span>
          <div><strong title={source.name}>{source.name}</strong><span>{source.pageCount ? `${source.pageCount} 页 · ` : ""}{formatBytes(source.size)}</span></div>
        </div>
        <div className="document-actions">
          <button className="icon-button" aria-label="更换 PDF" title="更换 PDF" onClick={onPick}><Icon name="swap_horiz" size={19} /></button>
          <button className="icon-button" aria-label="移除文件" title="移除文件" onClick={onClear}><Icon name="close" size={19} /></button>
        </div>
      </div>
      <embed className="pdf-frame" src={sourceUrl(source.id)} type="application/pdf" />
    </section>
  );
}

function RoundedSelect({ value, options, onChange, ariaLabel }: {
  value: ProviderName;
  options: Array<{ value: ProviderName; label: string }>;
  onChange: (value: ProviderName) => void;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: Event) => {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !menu.current?.contains(target)) setOpen(false);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const closeOnViewportChange = () => setOpen(false);
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("scroll", closeOnViewportChange, true);
    window.addEventListener("resize", closeOnViewportChange);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("scroll", closeOnViewportChange, true);
      window.removeEventListener("resize", closeOnViewportChange);
    };
  }, [open]);

  const triggerRect = root.current?.getBoundingClientRect();
  const estimatedMenuHeight = options.length * 40 + 20;
  const menuTop = triggerRect && triggerRect.bottom + 7 + estimatedMenuHeight > window.innerHeight
    ? triggerRect.top - estimatedMenuHeight - 7
    : (triggerRect?.bottom ?? 0) + 7;

  return (
    <div className="rounded-select" ref={root}>
      <button
        type="button"
        className={open ? "rounded-select-trigger open" : "rounded-select-trigger"}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
      >
        <span>{selected?.label}</span>
        <Icon name={open ? "expand_less" : "expand_more"} size={19} />
      </button>
      {open && triggerRect && createPortal(
        <div
          className="rounded-select-menu"
          role="listbox"
          aria-label={`${ariaLabel}选项`}
          ref={menu}
          style={{ left: triggerRect.left, top: menuTop, width: triggerRect.width }}
        >
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={option.value === value ? "selected" : ""}
              key={option.value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <span>{option.label}</span>
              {option.value === value && <Icon name="check" size={17} />}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}

function SettingsCard({ system, provider, onProvider, apiKey, onApiKey, model, onModel,
  baseUrl, onBaseUrl, ocrEnabled, onOcr, outputDir, onOutput, onPickOutput, canStart, onStart, busy,
  collapsed, onExpand }: {
  system: SystemInfo;
  provider: ProviderName;
  onProvider: (value: ProviderName) => void;
  apiKey: string;
  onApiKey: (value: string) => void;
  model: string;
  onModel: (value: string) => void;
  baseUrl: string;
  onBaseUrl: (value: string) => void;
  ocrEnabled: boolean;
  onOcr: (value: boolean) => void;
  outputDir: string;
  onOutput: (value: string) => void;
  onPickOutput: () => void;
  canStart: boolean;
  onStart: () => void;
  busy: boolean;
  collapsed: boolean;
  onExpand: () => void;
}) {
  const current = system.providers.find((item) => item.name === provider) ?? system.providers[0];
  if (collapsed) {
    return (
      <button type="button" className="glass-card settings-collapsed-bar" onClick={onExpand}>
        <span className="collapsed-settings-title"><Icon name="tune" size={19} /><strong>翻译设置</strong></span>
        <span className="collapsed-settings-summary">{current?.label} · {system.ocr.ready ? "OCR 就绪" : "OCR 未就绪"}</span>
        <span className="collapsed-settings-action">展开 <Icon name="expand_less" size={18} /></span>
      </button>
    );
  }
  return (
    <section className="glass-card settings-card">
      <div className="settings-scroll-content">
        <div className="form-grid">
          <label>
            <span>目标语言</span>
            <div className="static-select" aria-label="目标语言"><span>简体中文</span><Icon name="expand_more" size={19} /></div>
          </label>
          <label>
            <span>翻译服务</span>
            <RoundedSelect
              value={provider}
              options={system.providers.map((item) => ({ value: item.name, label: item.label }))}
              onChange={onProvider}
              ariaLabel="翻译服务"
            />
          </label>
        </div>
        {current?.requiresApiKey && (
          <label className="field-block">
            <span className="label-row"><span>API Key</span><small><Icon name="lock" size={13} /> 仅用于本次任务</small></span>
            <input type="password" value={apiKey} onChange={(event) => onApiKey(event.target.value)} placeholder="输入密钥" autoComplete="off" />
          </label>
        )}
        {provider !== "mock" && (
          <label className="field-block">
            <span className="label-row"><span>模型</span><button type="button" className="text-button">高级设置</button></span>
            <input value={model} onChange={(event) => onModel(event.target.value)} />
          </label>
        )}
        {provider === "compatible" && (
          <label className="field-block">
            <span>API 地址</span>
            <input
              type="url"
              value={baseUrl}
              onChange={(event) => onBaseUrl(event.target.value)}
              placeholder="https://api.example.com/v1"
            />
          </label>
        )}
        <div className="ocr-row">
          <div>
            <strong>OCR 识别</strong>
            <span className={system.ocr.ready ? "status ready" : "status"}>
              <i /> {system.ocr.ready ? "PP-OCRv6 已就绪" : "本地模型未就绪"}
            </span>
          </div>
          <button
            className={ocrEnabled ? "switch on" : "switch"}
            role="switch"
            aria-checked={ocrEnabled}
            disabled={!system.ocr.ready}
            onClick={() => onOcr(!ocrEnabled)}
          ><span /></button>
        </div>
        <div className="output-row">
          <label>
            <span>输出目录</span>
            <input value={outputDir} onChange={(event) => onOutput(event.target.value)} />
          </label>
          <button className="secondary-button" onClick={onPickOutput}>选择</button>
        </div>
        <button className="primary-button" disabled={!canStart || busy} onClick={onStart}>
          {busy ? <><span className="spinner" /> 正在处理</> : <><Icon name="translate" /> 开始翻译</>}
        </button>
        <p className="privacy-note"><Icon name="verified_user" size={15} /> 完整 PDF 不会作为单次请求发送，外部服务只接收受保护的文本段。</p>
      </div>
    </section>
  );
}

function ReadyPanel({ source, job }: { source: SourceDocument | null; job: JobState | null }) {
  if (job?.status === "running" || job?.status === "queued") return <ProgressPanel job={job} />;
  if (job && ["completed", "review"].includes(job.status)) return <OutputPanel job={job} />;
  if (job?.status === "failed") return <FailurePanel job={job} />;
  if (source) {
    return (
      <section className="preview-panel">
        <div className="document-preview">
          <Icon name="description" size={42} />
          <strong>{source.name}</strong>
          <span>PDF 已就绪，可以开始翻译</span>
        </div>
      </section>
    );
  }
  return (
    <section className="preview-panel ready-panel">
      <div className="ready-icon"><Icon name="g_translate" size={39} /></div>
      <h2>准备翻译</h2>
      <p>在左侧选择论文，配置完成后开始处理。</p>
    </section>
  );
}

function ProgressPanel({ job }: { job: JobState }) {
  const steps = ["分析 PDF", "恢复阅读顺序", "OCR 识别", "翻译正文", "调整页面布局", "生成并检查 PDF"];
  return (
    <section className="preview-panel progress-panel">
      <div className="progress-header">
        <div><span>正在处理</span><h2>{job.sourceName}</h2></div>
        <span className="running-pill"><span className="spinner" />运行中</span>
      </div>
      <div className="indeterminate"><span /></div>
      <div className="step-list">
        {steps.map((step, index) => (
          <div className={index === 0 ? "step active" : "step"} key={step}>
            <span>{index === 0 ? <Icon name="progress_activity" size={18} /> : index + 1}</span>
            <div><strong>{step}</strong>{index === 0 && <small>{job.message}</small>}</div>
          </div>
        ))}
      </div>
      <p className="progress-footnote">质量门完成前不会替换正式输出 PDF。</p>
    </section>
  );
}

function OutputPanel({ job }: { job: JobState }) {
  return (
    <section className="preview-panel result-panel">
      <div className="result-toolbar">
        <div><span className={job.status === "completed" ? "success-dot" : "review-dot"} />
          <strong>{job.status === "completed" ? "翻译完成" : "需要检查"}</strong></div>
        <button className="secondary-button" onClick={() => window.pywebview?.api?.open_output(job.id)}>
          <Icon name="folder_open" size={18} /> 打开文件夹
        </button>
      </div>
      <div className="output-document"><embed className="pdf-frame" src={artifactUrl(job.id, "output")} type="application/pdf" /></div>
      <div className="quality-strip">
        <span><Icon name="check_circle" size={17} /> 页面保持</span>
        <span><Icon name="check_circle" size={17} /> 无文字溢出</span>
        <span><Icon name="check_circle" size={17} /> 无区域碰撞</span>
      </div>
    </section>
  );
}

function FailurePanel({ job }: { job: JobState }) {
  return (
    <section className="preview-panel ready-panel failure-panel">
      <div className="ready-icon error"><Icon name="error" size={36} /></div>
      <h2>任务没有完成</h2><p>{job.message}</p>
    </section>
  );
}

function TextWorkspace() {
  const [source, setSource] = useState("");
  const [split, setSplit] = useStoredPercent("papertrans-text-split", 50);
  const workspace = useRef<HTMLDivElement>(null);
  const resize = (deltaX: number) => {
    const bounds = workspace.current?.getBoundingClientRect();
    if (!bounds) return;
    setSplit((current) => clamp(current + (deltaX / bounds.width) * 100, 32, 68));
  };
  return (
    <div className="text-workspace" ref={workspace} style={{ "--text-split": `${split}%` } as CSSProperties}>
      <section className="glass-card text-pane">
        <div className="pane-title"><strong>原文</strong><span>{source.length} 字符</span></div>
        <textarea value={source} onChange={(event) => setSource(event.target.value)} placeholder="在这里输入或粘贴需要翻译的文本……" />
      </section>
      <ResizeHandle orientation="vertical" label="调整原文与译文宽度" onDrag={resize} onNudge={(delta) => setSplit(clamp(split + delta, 32, 68))} />
      <section className="glass-card text-pane output-pane">
        <div className="pane-title"><strong>译文</strong><span className="beta-pill">下一阶段接入</span></div>
        <div className="text-empty"><Icon name="translate" size={34} /><p>输入文本后，这里将显示中文译文。</p></div>
      </section>
    </div>
  );
}

function LibraryPage() {
  return (
    <main className="content-page">
      <div className="page-heading"><div><span>本地任务</span><h1>仓库</h1></div><button className="primary-button compact"><Icon name="add" />新建翻译</button></div>
      <section className="glass-card library-card">
        <div className="library-empty"><Icon name="folder_open" size={40} /><h2>还没有翻译任务</h2><p>完成的 PDF 和文本任务会安全地保存在本地。</p></div>
      </section>
    </main>
  );
}

function SettingsPage({ system }: { system: SystemInfo }) {
  return (
    <main className="content-page settings-page">
      <div className="page-heading"><div><span>应用偏好</span><h1>设置</h1></div></div>
      <section className="glass-card preference-card">
        <h2>翻译服务</h2>
        {system.providers.filter((item) => item.name !== "mock").map((item) => (
          <div className="preference-row" key={item.name}><div><strong>{item.label}</strong><span>{item.defaultModel || "自定义模型"}</span></div><button className="secondary-button">配置</button></div>
        ))}
      </section>
      <section className="glass-card preference-card">
        <h2>本地 OCR</h2>
        <div className="preference-row"><div><strong>PP-OCRv6</strong><span>{system.ocr.ready ? "模型已就绪" : "未找到本地模型"}</span></div><span className={system.ocr.ready ? "status ready" : "status"}><i />{system.ocr.ready ? "可用" : "不可用"}</span></div>
      </section>
    </main>
  );
}

export function App() {
  const [view, setView] = useState<View>("translate");
  const [mode, setMode] = useState<InputMode>("pdf");
  const [system, setSystem] = useState<SystemInfo>(FALLBACK_SYSTEM);
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [provider, setProvider] = useState<ProviderName>("mock");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [outputDir, setOutputDir] = useState(FALLBACK_SYSTEM.defaultOutputDir);
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState("");
  const [sidebarSize, setSidebarSize] = useStoredPercent("papertrans-sidebar-size", 46);
  const [sourceSize, setSourceSize] = useStoredPercent("papertrans-source-size", 60);
  const [settingsCollapsed, setSettingsCollapsed] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const leftStack = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSystemInfo().then((info) => {
      setSystem(info);
      setOutputDir(info.defaultOutputDir);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    const selected = system.providers.find((item) => item.name === provider);
    setModel(selected?.defaultModel || "");
  }, [provider, system.providers]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      loadJob(job.id).then(setJob).catch((reason) => setError(reason.message));
    }, 900);
    return () => window.clearInterval(timer);
  }, [job]);

  const busy = job ? ["queued", "running"].includes(job.status) : false;
  const canStart = useMemo(() => Boolean(
    source
    && outputDir
    && (provider === "mock" || apiKey)
    && (provider !== "compatible" || (model && baseUrl)),
  ), [source, outputDir, provider, apiKey, model, baseUrl]);

  const acceptFile = async (file: File) => {
    setError("");
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件"); return;
    }
    try { setSource(await uploadPdf(file)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "PDF 导入失败"); }
  };

  const pickPdf = async () => {
    if (window.pywebview?.api?.pick_pdf) {
      try {
        const picked = await window.pywebview.api.pick_pdf();
        if (picked) setSource(await registerSource(picked.path));
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "PDF 导入失败");
      }
    } else fileInput.current?.click();
  };

  const pickOutput = async () => {
    const picked = await window.pywebview?.api?.pick_directory?.();
    if (picked) setOutputDir(picked);
  };

  const run = async () => {
    if (!source) return;
    setError("");
    try {
      setJob(await startJob({
        sourcePath: source.path,
        outputDir,
        provider,
        apiKey: apiKey || null,
        model: model || null,
        baseUrl: baseUrl || null,
        ocrEnabled,
        ocrModelDir: system.ocr.modelDir,
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "任务启动失败"); }
  };

  const resizeSidebar = (deltaX: number) => {
    const bounds = workspace.current?.getBoundingClientRect();
    if (!bounds) return;
    setSidebarSize((current) => clamp(current + (deltaX / bounds.width) * 100, 36, 56));
  };

  const adjustSourceSize = (deltaPercent: number) => {
    if (settingsCollapsed) {
      if (deltaPercent < 0) {
        setSettingsCollapsed(false);
        setSourceSize(SETTINGS_COLLAPSE_THRESHOLD - 2);
      }
      return;
    }
    const next = clamp(sourceSize + deltaPercent, 32, SETTINGS_COLLAPSE_THRESHOLD);
    setSourceSize(next);
    if (next >= SETTINGS_COLLAPSE_THRESHOLD && deltaPercent > 0) setSettingsCollapsed(true);
  };

  const resizeSource = (deltaY: number) => {
    const bounds = leftStack.current?.getBoundingClientRect();
    if (!bounds) return;
    adjustSourceSize((deltaY / bounds.height) * 100);
  };

  const clearSource = () => {
    setSource(null);
    setJob(null);
  };

  return (
    <div className="desktop-app">
      <Header view={view} onView={setView} />
      {view === "translate" && (
        <main className="translate-page">
          <div className="mode-row"><Segmented value={mode} onChange={setMode} /><span className="local-badge"><i /> 本地桌面运行</span></div>
          {error && <div className="error-banner"><Icon name="error" size={18} />{error}<button onClick={() => setError("")}><Icon name="close" size={17} /></button></div>}
          {mode === "text" ? <TextWorkspace /> : (
            <div className="workspace-grid" ref={workspace} style={{ "--sidebar-size": `${sidebarSize}%` } as CSSProperties}>
              <div className={settingsCollapsed ? "left-stack settings-collapsed" : "left-stack"} ref={leftStack} style={{ "--source-size": `${sourceSize}%` } as CSSProperties}>
                {source
                  ? <SourcePanel source={source} onPick={pickPdf} onDrop={acceptFile} onClear={clearSource} />
                  : <UploadCard onPick={pickPdf} onDrop={acceptFile} />}
                <ResizeHandle orientation="horizontal" label="调整源 PDF 与设置区域高度" onDrag={resizeSource} onNudge={adjustSourceSize} />
                <SettingsCard system={system} provider={provider} onProvider={setProvider} apiKey={apiKey} onApiKey={setApiKey}
                  model={model} onModel={setModel} baseUrl={baseUrl} onBaseUrl={setBaseUrl}
                  ocrEnabled={ocrEnabled} onOcr={setOcrEnabled} outputDir={outputDir}
                  onOutput={setOutputDir} onPickOutput={pickOutput} canStart={canStart} onStart={run} busy={busy}
                  collapsed={settingsCollapsed} onExpand={() => { setSettingsCollapsed(false); setSourceSize(60); }} />
              </div>
              <ResizeHandle orientation="vertical" label="调整源文件与译文区域宽度" onDrag={resizeSidebar} onNudge={(delta) => setSidebarSize(clamp(sidebarSize + delta, 36, 56))} />
              <ReadyPanel source={source} job={job} />
            </div>
          )}
          <input ref={fileInput} hidden type="file" accept="application/pdf,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0]; if (file) acceptFile(file);
          }} />
        </main>
      )}
      {view === "library" && <LibraryPage />}
      {view === "settings" && <SettingsPage system={system} />}
    </div>
  );
}

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Number(value.toFixed(2))));
}
