import { ChangeEvent, CSSProperties, Dispatch, DragEvent, KeyboardEvent, PointerEvent, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { artifactUrl, clearTemporaryUploads, clearTranslationCache, configureDesktopApi, deleteLibraryTask, libraryArtifactUrl, listProviderModels, loadJob, loadLibraryReadingMap, loadLibraryTask, loadLibraryTasks, loadReadingMap, loadStorageInfo, loadSystemInfo, openJobOutput, openLibraryTask, registerSource, releaseSource, sourceUrl, startJob, translateSelection, translateText, uploadPdf } from "./api";
import { closeDesktopWindow, isTauriDesktop, loadDesktopProviderConfigs, loadDesktopSession, minimizeDesktopWindow, pickDesktopDirectory, pickDesktopPdf, saveDesktopProviderConfig, setDesktopExitOnClose, setDesktopTheme, toggleDesktopMaximize, watchDesktopMaximized } from "./desktop";
import { PdfViewer } from "./PdfViewer";
import type { JobState, LibraryTaskDetail, LibraryTaskSummary, PageReadingMap, PdfTextSelection, ProviderName, SelectionTranslationResult, SourceDocument, StorageInfo, SystemInfo } from "./types";

const FALLBACK_SYSTEM: SystemInfo = {
  providers: [
    { name: "deepseek", label: "DeepSeek", defaultModel: "deepseek-v4-flash", requiresApiKey: true },
    { name: "kimi", label: "Kimi", defaultModel: "kimi-k2.6", requiresApiKey: true },
    { name: "zhipu", label: "智谱AI", defaultModel: "glm-4.6", requiresApiKey: true },
    { name: "compatible", label: "兼容接口", defaultModel: null, requiresApiKey: true },
    { name: "mock", label: "Mock 版式测试", defaultModel: null, requiresApiKey: false },
  ],
  ocr: { ready: false, modelDir: null },
  defaultOutputDir: ".papertrans/jobs",
};

type View = "translate" | "library" | "settings";
type ViewDirection = "forward" | "backward";
type AppTheme = "light" | "dark";
type ProviderDescriptor = SystemInfo["providers"][number];
type ProviderSessionConfig = {
  apiKey: string;
  model: string;
  baseUrl: string;
};
type ProviderSessionConfigs = Record<ProviderName, ProviderSessionConfig>;
type PendingConfirmation =
  | { kind: "delete-task"; task: LibraryTaskSummary }
  | { kind: "clear-cache" }
  | { kind: "clear-uploads" };
const VIEW_ORDER: Record<View, number> = { library: 0, translate: 1, settings: 2 };
const SETTINGS_COLLAPSE_THRESHOLD = 78;
const TEXT_COLLAPSE_THRESHOLD = 13;
const MAX_TEXT_TRANSLATION_CHARS = 20_000;

type TargetLanguage = "zh-CN" | "en" | "ja" | "ko" | "fr" | "es" | "de" | "ru";
const TARGET_LANGUAGES: Array<{ value: TargetLanguage; label: string }> = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "ko", label: "한국어" },
  { value: "fr", label: "Français" },
  { value: "es", label: "Español" },
  { value: "de", label: "Deutsch" },
  { value: "ru", label: "Русский" },
];
const DEFAULT_TARGET_LANGUAGE: TargetLanguage = "zh-CN";
const MENU_GAP = 6;
const MENU_MAX_HEIGHT = 208;

function createProviderSessionConfigs(system: SystemInfo): ProviderSessionConfigs {
  const configs: ProviderSessionConfigs = {
    mock: { apiKey: "", model: "", baseUrl: "" },
    deepseek: { apiKey: "", model: "", baseUrl: "" },
    kimi: { apiKey: "", model: "", baseUrl: "" },
    zhipu: { apiKey: "", model: "", baseUrl: "" },
    compatible: { apiKey: "", model: "", baseUrl: "" },
  };
  system.providers.forEach((item) => {
    configs[item.name].model = item.defaultModel ?? "";
  });
  return configs;
}

function providerIsConfigured(provider: ProviderDescriptor, config: ProviderSessionConfig): boolean {
  if (provider.name === "mock") return true;
  if (provider.requiresApiKey && !config.apiKey.trim()) return false;
  if (!config.model.trim()) return false;
  if (provider.name !== "compatible") return true;
  try {
    const url = new URL(config.baseUrl);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function modelDetectDisabledReason(provider: ProviderName, apiKey: string, baseUrl: string): string {
  if (provider === "mock") return "Mock 无需选择模型";
  if (!apiKey.trim()) return "请先填写 API Key 再检测";
  if (provider === "compatible" && !baseUrl.trim()) return "请先填写 API 地址再检测";
  return "";
}

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>;
}

function Header({ view, onView, maximized, onMaximized }: {
  view: View;
  onView: (view: View) => void;
  maximized: boolean;
  onMaximized: (value: boolean) => void;
}) {
  const toggleMaximize = async () => {
    onMaximized(await toggleDesktopMaximize());
  };
  const navigation = {
    library: { label: "仓库", icon: "library_books" },
    translate: { label: "翻译", icon: "translate" },
    settings: { label: "设置", icon: "settings" },
  } as const;
  const navIndex = VIEW_ORDER[view];
  return (
    <header className="app-header" data-tauri-drag-region>
      <button className="brand" onClick={() => onView("translate")}>PaperTrans</button>
      <nav aria-label="主导航" style={{ "--nav-index": navIndex } as CSSProperties}>
        <span className="nav-selection" aria-hidden="true" />
        {(["library", "translate", "settings"] as const).map((item) => (
          <button
            key={item}
            className={view === item ? "nav-item active" : "nav-item"}
            onClick={() => onView(item)}
          >
            <Icon name={navigation[item].icon} size={19} />
            <span>{navigation[item].label}</span>
          </button>
        ))}
      </nav>
      <div className="window-controls" aria-label="窗口控制">
        <button aria-label="最小化" title="最小化" onClick={() => void minimizeDesktopWindow()}><Icon name="remove" size={17} /></button>
        <button aria-label="最大化或还原" title="最大化或还原" onClick={() => void toggleMaximize()}><Icon name={maximized ? "filter_none" : "crop_square"} size={15} /></button>
        <button className="close-window" aria-label="关闭" title="关闭" onClick={() => void closeDesktopWindow()}><Icon name="close" size={18} /></button>
      </div>
    </header>
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

function useStoredBoolean(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    const saved = window.localStorage.getItem(key);
    return saved === null ? initial : saved === "true";
  });
  const update = (next: boolean) => {
    window.localStorage.setItem(key, String(next));
    setValue(next);
  };
  return [value, update];
}

function useStoredString(key: string, initial: string): [string, (value: string) => void] {
  const [value, setValue] = useState(() => window.localStorage.getItem(key) ?? initial);
  const update = (next: string) => {
    window.localStorage.setItem(key, next);
    setValue(next);
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

function SourcePanel({ source, onPick, onDrop, onClear, page, zoom, onPage, onPageCount, onZoom, readingMaps, activeFlowId, selectionOrigin, textSelection, selectionTranslation, selectionTranslationBusy, selectionTranslationError, onTranslateSelection, onDismissSelectionTranslation, onTextSelect, onFlowSelect, onFlowClear }: {
  source: SourceDocument;
  onPick: () => void;
  onDrop: (file: File) => void;
  onClear: () => void;
  page: number;
  zoom: number;
  onPage: (page: number) => void;
  onPageCount: (count: number) => void;
  onZoom: (zoom: number) => void;
  readingMaps: Record<number, PageReadingMap>;
  activeFlowId: string | null;
  selectionOrigin: "source" | "translation" | null;
  textSelection: PdfTextSelection | null;
  selectionTranslation: SelectionTranslationResult | null;
  selectionTranslationBusy: boolean;
  selectionTranslationError: string;
  onTranslateSelection: () => void;
  onDismissSelectionTranslation: () => void;
  onTextSelect: (flowId: string, selectedText: string) => void;
  onFlowSelect: (flowId: string, targetPage?: number) => void;
  onFlowClear: () => void;
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
      <PdfViewer url={sourceUrl(source.id)} pageNumber={page} zoom={zoom} label="原文 PDF"
        onPageChange={onPage} onPageCount={onPageCount} onZoomChange={onZoom}
        readingMaps={readingMaps} mappingSide="source" activeFlowId={activeFlowId}
        selectionOrigin={selectionOrigin} textSelection={textSelection}
        selectionTranslation={selectionTranslation} selectionTranslationBusy={selectionTranslationBusy}
        selectionTranslationError={selectionTranslationError} onTranslateSelection={onTranslateSelection}
        onDismissSelectionTranslation={onDismissSelectionTranslation}
        onTextSelect={onTextSelect}
        onFlowSelect={onFlowSelect} onFlowClear={onFlowClear} />
    </section>
  );
}

function RoundedSelect<T extends string>({ value, options, onChange, ariaLabel }: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
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
    const closeOnScroll = (event: Event) => {
      // Scrolling inside the menu itself browses the options; only a scroll of the
      // underlying page or card (which would detach the fixed menu) closes it.
      if (menu.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("resize", closeOnViewportChange);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("resize", closeOnViewportChange);
    };
  }, [open]);

  const triggerRect = root.current?.getBoundingClientRect();
  // Cap the popup to a fixed scrollable height so every select — regardless of how
  // many options it carries — makes the same up/down decision at the same position.
  const menuHeight = Math.min(options.length * 33 + 10, MENU_MAX_HEIGHT);
  const spaceBelow = triggerRect ? window.innerHeight - triggerRect.bottom : 0;
  const openUpward = Boolean(
    triggerRect
    && spaceBelow < MENU_MAX_HEIGHT + MENU_GAP
    && triggerRect.top > spaceBelow,
  );
  const menuTop = !triggerRect
    ? 0
    : openUpward
      ? triggerRect.top - menuHeight - MENU_GAP
      : triggerRect.bottom + MENU_GAP;

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

function ModelCombobox({ value, onChange, detect, detectDisabledReason, placeholder, disabled }: {
  value: string;
  onChange: (value: string) => void;
  detect: () => Promise<string[]>;
  detectDisabledReason: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  const runDetect = async () => {
    setLoading(true);
    setError("");
    try {
      setModels(await detect());
    } catch (reason) {
      setModels([]);
      setError(reason instanceof Error ? reason.message : "模型检测失败");
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    if (disabled) return;
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!detectDisabledReason && !models.length && !loading) void runDetect();
  };

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: Event) => {
      const target = event.target as Node;
      if (!root.current?.contains(target) && !menu.current?.contains(target)) setOpen(false);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const closeOnScroll = (event: Event) => {
      if (menu.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    const closeOnResize = () => setOpen(false);
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("resize", closeOnResize);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("resize", closeOnResize);
    };
  }, [open]);

  const triggerRect = root.current?.getBoundingClientRect();
  const menuHeight = Math.min(Math.max(models.length, 1) * 33 + 10, MENU_MAX_HEIGHT);
  const spaceBelow = triggerRect ? window.innerHeight - triggerRect.bottom : 0;
  const openUpward = Boolean(
    triggerRect && spaceBelow < MENU_MAX_HEIGHT + MENU_GAP && triggerRect.top > spaceBelow,
  );
  const menuTop = !triggerRect
    ? 0
    : openUpward
      ? triggerRect.top - menuHeight - MENU_GAP
      : triggerRect.bottom + MENU_GAP;

  return (
    <div className="rounded-select model-combobox" ref={root}>
      <div className={open ? "model-combobox-field open" : "model-combobox-field"}>
        <input
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          aria-label="模型"
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="model-detect-toggle"
          aria-label="检测可用模型"
          aria-expanded={open}
          disabled={disabled}
          title={detectDisabledReason || "检测可用模型"}
          onClick={toggle}
        >
          {loading ? <span className="spinner" /> : <Icon name={open ? "expand_less" : "expand_more"} size={19} />}
        </button>
      </div>
      {open && triggerRect && createPortal(
        <div
          className="rounded-select-menu model-combobox-menu"
          role="listbox"
          aria-label="可用模型"
          ref={menu}
          style={{ left: triggerRect.left, top: menuTop, width: triggerRect.width }}
        >
          {detectDisabledReason ? (
            <div className="model-combobox-hint">{detectDisabledReason}</div>
          ) : loading ? (
            <div className="model-combobox-hint"><span className="spinner" />正在检测可用模型……</div>
          ) : error ? (
            <div className="model-combobox-hint error">
              <span><Icon name="error" size={16} />{error}</span>
              <button type="button" className="text-button" onClick={() => void runDetect()}>重试</button>
            </div>
          ) : models.length === 0 ? (
            <div className="model-combobox-hint">未检测到可用模型</div>
          ) : (
            models.map((item) => (
              <button
                type="button"
                role="option"
                aria-selected={item === value}
                className={item === value ? "selected" : ""}
                key={item}
                onClick={() => {
                  onChange(item);
                  setOpen(false);
                }}
              >
                <span>{item}</span>
                {item === value && <Icon name="check" size={17} />}
              </button>
            ))
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}

function SettingsCard({ system, provider, onProvider, targetLanguage, onTargetLanguage, apiKey, onApiKey, model, onModel,
  baseUrl, onBaseUrl, ocrEnabled, onOcr, outputDir, onOutput, onPickOutput, canStart, onStart, busy,
  collapsed, onExpand }: {
  system: SystemInfo;
  provider: ProviderName;
  onProvider: (value: ProviderName) => void;
  targetLanguage: TargetLanguage;
  onTargetLanguage: (value: TargetLanguage) => void;
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
        <span className="collapsed-settings-summary" aria-hidden="true" />
        <span className="collapsed-settings-action">展开 <Icon name="expand_less" size={18} /></span>
      </button>
    );
  }
  return (
    <section className="glass-card settings-card">
      <div className="settings-scroll-content">
        <div className="settings-section-title">
          <span><Icon name="tune" size={17} /><strong>翻译设置</strong></span>
          <small>Translation Settings</small>
        </div>
        <div className="form-grid">
          <div className="field">
            <span>目标语言</span>
            <RoundedSelect
              value={targetLanguage}
              options={TARGET_LANGUAGES}
              onChange={onTargetLanguage}
              ariaLabel="目标语言"
            />
          </div>
          <div className="field">
            <span>翻译服务</span>
            <RoundedSelect
              value={provider}
              options={system.providers.map((item) => ({ value: item.name, label: item.label }))}
              onChange={onProvider}
              ariaLabel="翻译服务"
            />
          </div>
        </div>
        {current?.requiresApiKey && (
          <div className="field field-block">
            <span className="label-row"><span>API Key</span><small><Icon name="lock" size={13} /> 仅用于本次任务</small></span>
            <input type="password" value={apiKey} onChange={(event) => onApiKey(event.target.value)} placeholder="输入密钥" autoComplete="off" aria-label="API Key" />
          </div>
        )}
        {provider !== "mock" && (
          <div className="field field-block">
            <span>模型</span>
            <ModelCombobox
              value={model}
              onChange={onModel}
              detect={() => listProviderModels({ provider, apiKey, baseUrl: baseUrl || null })}
              detectDisabledReason={modelDetectDisabledReason(provider, apiKey, baseUrl)}
              placeholder="输入模型名，或点击右侧检测"
            />
          </div>
        )}
        {provider === "compatible" && (
          <div className="field field-block">
            <span>API 地址</span>
            <input
              type="url"
              value={baseUrl}
              onChange={(event) => onBaseUrl(event.target.value)}
              placeholder="https://api.example.com/v1"
              aria-label="API 地址"
            />
          </div>
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
          <div className="field">
            <span>输出目录</span>
            <input value={outputDir} onChange={(event) => onOutput(event.target.value)} aria-label="输出目录" />
          </div>
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

function ReadyPanel({ source, job, restoredTask, page, zoom, onPage, onPageCount, onZoom, readingMaps, activeFlowId, selectionOrigin, textSelection, onFlowSelect, onFlowClear }: {
  source: SourceDocument | null;
  job: JobState | null;
  restoredTask: LibraryTaskDetail | null;
  page: number;
  zoom: number;
  onPage: (page: number) => void;
  onPageCount: (count: number) => void;
  onZoom: (zoom: number) => void;
  readingMaps: Record<number, PageReadingMap>;
  activeFlowId: string | null;
  selectionOrigin: "source" | "translation" | null;
  textSelection: PdfTextSelection | null;
  onFlowSelect: (flowId: string, targetPage?: number) => void;
  onFlowClear: () => void;
}) {
  if (job?.status === "running" || job?.status === "queued") return <ProgressPanel job={job} />;
  if (restoredTask?.kind === "pdf" && restoredTask.outputPdf) return <OutputPanel status="completed" outputUrl={libraryArtifactUrl(restoredTask.id, "output")} onOpen={() => void openLibraryTask(restoredTask.id)} page={page} zoom={zoom} onPage={onPage} onPageCount={onPageCount} onZoom={onZoom} readingMaps={readingMaps} activeFlowId={activeFlowId} selectionOrigin={selectionOrigin} textSelection={textSelection} onFlowSelect={onFlowSelect} onFlowClear={onFlowClear} />;
  if (job?.outputAvailable && (job.status === "completed" || job.status === "review")) return <OutputPanel status={job.status} outputUrl={artifactUrl(job.id, "output")} onOpen={() => void openJobOutput(job.id)} page={page} zoom={zoom} onPage={onPage} onPageCount={onPageCount} onZoom={onZoom} readingMaps={readingMaps} activeFlowId={activeFlowId} selectionOrigin={selectionOrigin} textSelection={textSelection} onFlowSelect={onFlowSelect} onFlowClear={onFlowClear} />;
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
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    setElapsedSeconds(0);
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job.id]);

  return (
    <section className="preview-panel progress-panel">
      <div className="progress-header">
        <div><span>正在处理</span><h2>{job.sourceName}</h2></div>
        <span className="running-pill"><span className="spinner" />运行中</span>
      </div>
      <div className="indeterminate"><span /></div>
      <div className="progress-live" role="status" aria-live="polite">
        <span className="progress-orbit" aria-hidden="true" />
        <div className="progress-live-copy">
          <strong>正在执行本地翻译流水线</strong>
          <span>{job.message}</span>
          <small>已运行 {formatElapsed(elapsedSeconds)}</small>
        </div>
      </div>
      <p className="progress-footnote">质量门完成前不会替换正式输出 PDF。</p>
    </section>
  );
}

function OutputPanel({ status, outputUrl, onOpen, page, zoom, onPage, onPageCount, onZoom, readingMaps, activeFlowId, selectionOrigin, textSelection, onFlowSelect, onFlowClear }: {
  status: "completed" | "review";
  outputUrl: string;
  onOpen: () => void;
  page: number;
  zoom: number;
  onPage: (page: number) => void;
  onPageCount: (count: number) => void;
  onZoom: (zoom: number) => void;
  readingMaps: Record<number, PageReadingMap>;
  activeFlowId: string | null;
  selectionOrigin: "source" | "translation" | null;
  textSelection: PdfTextSelection | null;
  onFlowSelect: (flowId: string, targetPage?: number) => void;
  onFlowClear: () => void;
}) {
  return (
    <section className="preview-panel result-panel">
      <div className="result-toolbar">
        <div aria-label={status === "completed" ? "任务已完成" : "任务需要检查"} title={status === "completed" ? "任务已完成" : "任务需要检查"}>
          <span className={status === "completed" ? "success-dot" : "review-dot"} />
        </div>
        <button className="icon-button outlined-icon-button" aria-label="打开任务文件夹" title="打开任务文件夹" onClick={onOpen}>
          <Icon name="folder_open" size={18} />
        </button>
      </div>
      <div className="output-document"><PdfViewer url={outputUrl} pageNumber={page} zoom={zoom} label="译文 PDF"
        onPageChange={onPage} onPageCount={onPageCount} onZoomChange={onZoom}
        readingMaps={readingMaps} mappingSide="translation" activeFlowId={activeFlowId}
        selectionOrigin={selectionOrigin} textSelection={textSelection}
        onFlowSelect={onFlowSelect} onFlowClear={onFlowClear} /></div>
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

function CollapsedTextBar({ title, summary, icon, onExpand }: {
  title: string;
  summary: string;
  icon: string;
  onExpand: () => void;
}) {
  return (
    <button type="button" className="glass-card text-collapsed-bar" onClick={onExpand}>
      <span className="text-bar-title"><Icon name={icon} size={18} /><strong>{title}</strong></span>
      <span className="text-bar-summary">{summary}</span>
      <span className="text-bar-action">展开 <Icon name="expand_more" size={18} /></span>
    </button>
  );
}

function TextSourcePanel({ value, onChange, onTranslate, canTranslate, busy, collapsed, onExpand }: {
  value: string;
  onChange: (value: string) => void;
  onTranslate: () => void;
  canTranslate: boolean;
  busy: boolean;
  collapsed: boolean;
  onExpand: () => void;
}) {
  if (collapsed) {
    return <CollapsedTextBar title="文本原文" summary={value ? `${value.length} 字符` : ""} icon="text_fields" onExpand={onExpand} />;
  }
  return (
    <section className="glass-card text-dock text-source-dock">
      <div className="text-dock-header">
        <span className="text-dock-title"><Icon name="text_fields" size={18} /><strong>文本原文</strong></span>
        <span className="text-dock-actions">
          <span>{value.length} 字符</span>
          <button
            type="button"
            className="text-translate-button"
            disabled={!canTranslate || busy}
            onClick={onTranslate}
          >
            {busy ? <><span className="spinner" />翻译中</> : <><Icon name="translate" size={16} />翻译文本</>}
          </button>
        </span>
      </div>
      <textarea
        value={value}
        maxLength={MAX_TEXT_TRANSLATION_CHARS}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && canTranslate && !busy) {
            event.preventDefault();
            onTranslate();
          }
        }}
        placeholder="在这里输入或粘贴需要翻译的文本……"
      />
    </section>
  );
}

function TextOutputPanel({ source, translation, busy, error, providerLabel, collapsed, onExpand }: {
  source: string;
  translation: string;
  busy: boolean;
  error: string;
  providerLabel: string;
  collapsed: boolean;
  onExpand: () => void;
}) {
  const summary = busy ? "正在翻译" : error ? "翻译失败" : translation ? "译文已生成" : source ? "等待翻译" : "";
  if (collapsed) {
    return <CollapsedTextBar title="文本译文" summary={summary} icon="translate" onExpand={onExpand} />;
  }
  return (
    <section className="glass-card text-dock text-output-dock">
      <div className="text-dock-header">
        <span className="text-dock-title"><Icon name="translate" size={18} /><strong>文本译文</strong></span>
        <span className={error ? "text-result-status error" : translation ? "text-result-status success" : "text-result-status"}>
          {busy ? "处理中" : translation ? providerLabel : error ? "失败" : "待翻译"}
        </span>
      </div>
      {busy ? (
        <div className="text-dock-empty text-translation-state"><span className="spinner" /><span>正在通过 {providerLabel} 翻译文本……</span></div>
      ) : error ? (
        <div className="text-dock-empty text-translation-state error"><Icon name="error" size={24} /><span>{error}</span></div>
      ) : translation ? (
        <textarea className="text-output-content" value={translation} readOnly aria-label="文本译文内容" />
      ) : (
        <div className="text-dock-empty">
          <Icon name="translate" size={28} />
          <span>{source ? "点击左侧“翻译文本”，这里显示中文译文。" : "输入文本后，这里显示中文译文。"}</span>
        </div>
      )}
    </section>
  );
}

function LibraryPage({ direction, tasks, loading, error, onRestoreText, onRestorePdf, onOpen, onDelete }: {
  direction: ViewDirection;
  tasks: LibraryTaskSummary[];
  loading: boolean;
  error: string;
  onRestoreText: (task: LibraryTaskSummary) => void;
  onRestorePdf: (task: LibraryTaskSummary) => void;
  onOpen: (task: LibraryTaskSummary) => void;
  onDelete: (task: LibraryTaskSummary) => void;
}) {
  return (
    <main className={`content-page library-page view-stage view-${direction}`}>
      <section className="library-card">
        {loading ? (
          <div className="library-empty"><span className="spinner library-spinner" /><h2>正在读取本地任务</h2></div>
        ) : error ? (
          <div className="library-empty library-error"><Icon name="error" size={40} /><h2>仓库暂时不可用</h2><p>{error}</p></div>
        ) : (
          <div className="library-columns">
            {(["pdf", "text"] as const).map((kind) => {
              const group = tasks.filter((task) => task.kind === kind);
              return (
                <section className="glass-card library-group" key={kind}>
                  <header><div><Icon name={kind === "pdf" ? "picture_as_pdf" : "text_snippet"} size={20} /><strong>{kind === "pdf" ? "PDF 翻译" : "文本翻译"}</strong></div><span>{group.length}</span></header>
                  {group.length === 0 ? <div className="library-group-empty">暂无{kind === "pdf" ? " PDF " : "文本"}任务</div> : (
                    <div className="library-list">
                      {group.map((task) => {
                        const restorable = task.kind === "text" || task.status === "completed";
                        const displayTitle = task.kind === "text" ? task.preview || task.title : task.title;
                        return (
                          <article className={restorable ? "library-row restorable" : "library-row"} key={task.id}
                            role={restorable ? "button" : undefined} tabIndex={restorable ? 0 : undefined}
                            onClick={() => restorable && (task.kind === "pdf" ? onRestorePdf(task) : onRestoreText(task))}
                            onKeyDown={(event) => {
                              if (restorable && (event.key === "Enter" || event.key === " ")) {
                                event.preventDefault();
                                task.kind === "pdf" ? onRestorePdf(task) : onRestoreText(task);
                              }
                            }}>
                            <div className="library-kind"><Icon name={task.kind === "pdf" ? "picture_as_pdf" : "text_snippet"} size={21} /></div>
                            <div className="library-main">
                              <strong className="library-task-title" title={displayTitle}>{displayTitle}</strong>
                              <span>{task.provider} · {formatLibraryTime(task.updatedAt)}</span>
                            </div>
                            <span className={`library-status status-${task.status}`}>{libraryStatusLabel(task.status)}</span>
                            <div className="library-actions">
                              <button className="icon-button outlined-icon-button library-action"
                                aria-label={task.kind === "pdf" ? "打开任务文件夹" : "恢复文本任务"}
                                title={task.kind === "pdf" ? "打开任务文件夹" : "恢复文本任务"}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  task.kind === "pdf" ? onOpen(task) : onRestoreText(task);
                                }}>
                                <Icon name={task.kind === "pdf" ? "folder_open" : "restore"} size={18} />
                              </button>
                              <button className="icon-button outlined-icon-button library-action library-delete-action"
                                aria-label="删除任务" title="删除任务"
                                disabled={task.status === "queued" || task.status === "running"}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onDelete(task);
                                }}>
                                <Icon name="delete" size={18} />
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

function ProviderConfigDialog({ provider, config, onCancel, onSave }: {
  provider: ProviderDescriptor;
  config: ProviderSessionConfig;
  onCancel: () => void;
  onSave: (config: ProviderSessionConfig) => Promise<void>;
}) {
  const [draft, setDraft] = useState(config);
  const [showApiKey, setShowApiKey] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [saving, setSaving] = useState(false);
  const apiKeyInput = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const onCancelRef = useRef(onCancel);
  const savingRef = useRef(saving);
  onCancelRef.current = onCancel;
  savingRef.current = saving;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusFrame = window.requestAnimationFrame(() => apiKeyInput.current?.focus());
    const handleDialogKeys = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!savingRef.current) onCancelRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>("button, input, select, textarea, [tabindex]:not([tabindex='-1'])") ?? [])]
        .filter((element) => !element.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleDialogKeys);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleDialogKeys);
      previouslyFocused?.focus();
    };
  }, []);

  const updateDraft = (patch: Partial<ProviderSessionConfig>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setValidationError("");
  };

  const submit = async () => {
    const normalized = {
      apiKey: draft.apiKey.trim(),
      model: draft.model.trim(),
      baseUrl: draft.baseUrl.trim(),
    };
    if (provider.requiresApiKey && !normalized.apiKey) {
      setValidationError("请输入 API Key");
      return;
    }
    if (!normalized.model) {
      setValidationError("请输入模型名称");
      return;
    }
    if (provider.name === "compatible") {
      try {
        const url = new URL(normalized.baseUrl);
        if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsupported protocol");
      } catch {
        setValidationError("请输入有效的 HTTP(S) API 地址");
        return;
      }
    }
    setSaving(true);
    try {
      await onSave(normalized);
    } catch (reason) {
      setValidationError(reason instanceof Error ? reason.message : typeof reason === "string" ? reason : "配置保存失败，请重试");
      setSaving(false);
    }
  };

  return createPortal(
    <div
      className="provider-dialog-backdrop"
      onPointerDown={(event) => {
        if (!saving && event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        ref={dialog}
        className="provider-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="provider-dialog-title"
        aria-describedby="provider-dialog-privacy"
      >
        <header>
          <div>
            <span className="provider-dialog-icon"><Icon name="key" size={20} /></span>
            <div><small>翻译服务</small><h2 id="provider-dialog-title">配置 {provider.label}</h2></div>
          </div>
          <button type="button" className="icon-button" aria-label="关闭配置窗口" title="关闭" disabled={saving} onClick={onCancel}><Icon name="close" size={18} /></button>
        </header>
        <form noValidate onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <div className="field field-block">
            <span>API Key</span>
            <div className="provider-secret-field">
              <input
                ref={apiKeyInput}
                type={showApiKey ? "text" : "password"}
                value={draft.apiKey}
                onChange={(event) => updateDraft({ apiKey: event.target.value })}
                placeholder={`输入 ${provider.label} API Key`}
                autoComplete="off"
                disabled={saving}
                aria-label="API Key"
              />
              <button type="button" disabled={saving} aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"} title={showApiKey ? "隐藏 API Key" : "显示 API Key"} onClick={() => setShowApiKey((current) => !current)}>
                <Icon name={showApiKey ? "visibility_off" : "visibility"} size={18} />
              </button>
            </div>
          </div>
          <div className="field field-block">
            <span>模型</span>
            <ModelCombobox
              value={draft.model}
              onChange={(value) => updateDraft({ model: value })}
              detect={() => listProviderModels({ provider: provider.name, apiKey: draft.apiKey, baseUrl: draft.baseUrl || null })}
              detectDisabledReason={modelDetectDisabledReason(provider.name, draft.apiKey, draft.baseUrl)}
              placeholder="输入模型名，或点击右侧检测"
              disabled={saving}
            />
          </div>
          {provider.name === "compatible" && (
            <div className="field field-block">
              <span>API 地址</span>
              <input type="url" value={draft.baseUrl} disabled={saving} onChange={(event) => updateDraft({ baseUrl: event.target.value })} placeholder="https://api.example.com/v1" aria-label="API 地址" />
            </div>
          )}
          {validationError && <div className="provider-dialog-error" role="alert"><Icon name="error" size={17} />{validationError}</div>}
          <p className="provider-dialog-privacy" id="provider-dialog-privacy"><Icon name="shield_lock" size={16} />配置安全保存在 Windows 凭据管理器，不写入浏览器存储、任务记录、诊断或缓存。</p>
          <footer>
            <button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>取消</button>
            <button type="submit" className="primary-button compact" disabled={saving}>{saving ? <><span className="spinner" />正在保存</> : "保存配置"}</button>
          </footer>
        </form>
      </section>
    </div>,
    document.body,
  );
}

function ConfirmationDialog({ action, busy, error, onCancel, onConfirm }: {
  action: PendingConfirmation;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const confirmButton = useRef<HTMLButtonElement>(null);
  const copy = action.kind === "delete-task"
    ? {
        eyebrow: "删除本地记录",
        title: `删除${action.task.kind === "pdf" ? " PDF" : "文本"}任务？`,
        message: action.task.kind === "pdf"
          ? "仓库记录会被删除，但原始论文和已经生成的译文文件都会保留。"
          : "仓库记录以及 PaperTrans 内部保存的文本原文和译文会被删除。",
        confirm: "删除任务",
        icon: "delete",
      }
    : action.kind === "clear-cache"
      ? {
          eyebrow: "本地存储",
          title: "清理翻译缓存？",
          message: "任务历史和译文文件不会删除；之后翻译相同内容可能需要重新调用服务并产生费用。",
          confirm: "清理缓存",
          icon: "cached",
        }
      : {
          eyebrow: "本地存储",
          title: "清理临时文件？",
          message: "只会移除未被当前页面、运行任务或仓库记录引用的上传副本。",
          confirm: "清理临时文件",
          icon: "delete_sweep",
        };

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => confirmButton.current?.focus());
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [busy, onCancel]);

  return createPortal(
    <div className="provider-dialog-backdrop confirmation-backdrop" onPointerDown={(event) => {
      if (!busy && event.target === event.currentTarget) onCancel();
    }}>
      <section className="confirmation-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-message">
        <span className="confirmation-icon"><Icon name={copy.icon} size={22} /></span>
        <div className="confirmation-copy"><small>{copy.eyebrow}</small><h2 id="confirmation-title">{copy.title}</h2><p id="confirmation-message">{copy.message}</p></div>
        {error && <div className="provider-dialog-error confirmation-error" role="alert"><Icon name="error" size={17} />{error}</div>}
        <footer>
          <button className="secondary-button" disabled={busy} onClick={onCancel}>取消</button>
          <button ref={confirmButton} className={action.kind === "delete-task" ? "danger-button" : "primary-button compact"} disabled={busy} onClick={onConfirm}>
            {busy ? <><span className="spinner" />正在处理</> : copy.confirm}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function SettingsPage({ system, direction, providerConfigs, providerConfigError, onConfigure, exitOnClose, onExitOnClose, theme, onTheme, outputDir, onOutput, onPickOutput, onResetOutput, pageSync, onPageSync, zoomSync, onZoomSync, storage, storageError, onClearCache, onClearUploads }: {
  system: SystemInfo;
  direction: ViewDirection;
  providerConfigs: ProviderSessionConfigs;
  providerConfigError: string;
  onConfigure: (provider: ProviderName) => void;
  exitOnClose: boolean;
  onExitOnClose: (value: boolean) => void;
  theme: AppTheme;
  onTheme: (value: AppTheme) => void;
  outputDir: string;
  onOutput: (value: string) => void;
  onPickOutput: () => void;
  onResetOutput: () => void;
  pageSync: boolean;
  onPageSync: (value: boolean) => void;
  zoomSync: boolean;
  onZoomSync: (value: boolean) => void;
  storage: StorageInfo | null;
  storageError: string;
  onClearCache: () => void;
  onClearUploads: () => void;
}) {
  return (
    <main className={`content-page settings-page view-stage view-${direction}`}>
      <section className="glass-card preference-card">
        <h2>应用行为</h2>
        <div className="preference-row">
          <div><strong>关闭主窗口时退出应用</strong></div>
          <button className={exitOnClose ? "switch on" : "switch"} role="switch" aria-checked={exitOnClose} onClick={() => onExitOnClose(!exitOnClose)}><span /></button>
        </div>
        <div className="preference-row">
          <div><strong>暗色主题</strong></div>
          <button className={theme === "dark" ? "switch on" : "switch"} role="switch" aria-checked={theme === "dark"} onClick={() => onTheme(theme === "dark" ? "light" : "dark")}><span /></button>
        </div>
      </section>
      <section className="glass-card preference-card">
        <h2>PDF 输出</h2>
        <div className="field preference-path">
          <span>默认输出目录</span>
          <div>
            <input aria-label="默认输出目录" value={outputDir} onChange={(event) => onOutput(event.target.value)} />
            <button className="secondary-button" type="button" onClick={onPickOutput}>选择文件夹</button>
            <button className="text-button" type="button" onClick={onResetOutput}>恢复默认</button>
          </div>
          <small>新启动的 PDF 翻译会保存到此目录；不会移动已有任务。</small>
        </div>
      </section>
      <section className="glass-card preference-card">
        <h2>翻译服务</h2>
        {providerConfigError && <div className="provider-config-load-error" role="alert"><Icon name="error" size={17} />{providerConfigError}</div>}
        {system.providers.filter((item) => item.name !== "mock").map((item) => {
          const configured = providerIsConfigured(item, providerConfigs[item.name]);
          return (
            <div className="preference-row" key={item.name}>
              <div>
                <strong>{item.label}</strong>
                <span>{providerConfigs[item.name].model || item.defaultModel || "自定义模型"}</span>
              </div>
              <div className="provider-config-actions">
                <span className={configured ? "provider-config-indicator configured" : "provider-config-indicator"} aria-label={configured ? "已配置" : "未配置"} title={configured ? "已配置" : "未配置"} />
                <button className="secondary-button" onClick={() => onConfigure(item.name)}>{configured ? "编辑" : "配置"}</button>
              </div>
            </div>
          );
        })}
      </section>
      <section className="glass-card preference-card storage-card">
        <h2>本地存储</h2>
        {storageError && <div className="provider-config-load-error" role="alert"><Icon name="error" size={17} />{storageError}</div>}
        <div className="preference-row">
          <div><strong>翻译缓存</strong><span>{storage ? `${formatBytes(storage.cache.bytes)} · ${storage.cache.fileCount} 个文件` : "正在统计"}</span></div>
          <button className="secondary-button storage-action" disabled={!storage || storage.cache.fileCount === 0} onClick={onClearCache}><Icon name="cached" size={17} />清理</button>
        </div>
        <div className="preference-row">
          <div><strong>临时上传</strong><span>{storage ? `${formatBytes(storage.temporaryUploads.bytes)} · ${storage.temporaryUploads.fileCount} 个文件` : "正在统计"}</span></div>
          <button className="secondary-button storage-action" disabled={!storage || storage.temporaryUploads.fileCount === 0} onClick={onClearUploads}><Icon name="delete_sweep" size={17} />清理</button>
        </div>
        <p className="storage-safety-note"><Icon name="shield_lock" size={16} />清理操作不会删除原始论文、仓库任务或已经生成的译文文件。</p>
      </section>
      <section className="glass-card preference-card">
        <h2>本地 OCR</h2>
        <div className="preference-row"><div><strong>PP-OCRv6</strong><span>{system.ocr.ready ? "模型已就绪" : "未找到本地模型"}</span></div><span className={system.ocr.ready ? "status ready" : "status"}><i />{system.ocr.ready ? "可用" : "不可用"}</span></div>
      </section>
      <section className="glass-card preference-card">
        <h2>PDF 阅读器</h2>
        <div className="preference-row">
          <div><strong>同步翻页</strong><span>在任意一侧翻页时同步另一侧</span></div>
          <button className={pageSync ? "switch on" : "switch"} role="switch" aria-checked={pageSync} onClick={() => onPageSync(!pageSync)}><span /></button>
        </div>
        <div className="preference-row">
          <div><strong>同步缩放</strong><span>在任意一侧缩放时同步另一侧</span></div>
          <button className={zoomSync ? "switch on" : "switch"} role="switch" aria-checked={zoomSync} onClick={() => onZoomSync(!zoomSync)}><span /></button>
        </div>
      </section>
    </main>
  );
}

export function App() {
  const [view, setView] = useState<View>("translate");
  const [viewDirection, setViewDirection] = useState<ViewDirection>("forward");
  const [system, setSystem] = useState<SystemInfo>(FALLBACK_SYSTEM);
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [textSource, setTextSource] = useState("");
  const [textTranslation, setTextTranslation] = useState("");
  const [textTranslationError, setTextTranslationError] = useState("");
  const [textTranslationBusy, setTextTranslationBusy] = useState(false);
  const [libraryTasks, setLibraryTasks] = useState<LibraryTaskSummary[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [storageError, setStorageError] = useState("");
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [confirmationBusy, setConfirmationBusy] = useState(false);
  const [confirmationError, setConfirmationError] = useState("");
  const [provider, setProvider] = useStoredString("papertrans-provider", "mock") as [ProviderName, (value: ProviderName) => void];
  const [providerConfigs, setProviderConfigs] = useState<ProviderSessionConfigs>(() => createProviderSessionConfigs(FALLBACK_SYSTEM));
  const [providerConfigError, setProviderConfigError] = useState("");
  const [configuringProvider, setConfiguringProvider] = useState<ProviderName | null>(null);
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [targetLanguage, setTargetLanguage] = useStoredString("papertrans-target-language", DEFAULT_TARGET_LANGUAGE) as [TargetLanguage, (value: TargetLanguage) => void];
  const [outputDir, setOutputDir] = useStoredString("papertrans-output-directory", FALLBACK_SYSTEM.defaultOutputDir);
  const [job, setJob] = useState<JobState | null>(null);
  const [restoredTextTaskId, setRestoredTextTaskId] = useState<string | null>(null);
  const [restoredPdfTask, setRestoredPdfTask] = useState<LibraryTaskDetail | null>(null);
  const [sourcePdfPage, setSourcePdfPage] = useState(1);
  const [outputPdfPage, setOutputPdfPage] = useState(1);
  const [sourcePdfPageCount, setSourcePdfPageCount] = useState(0);
  const [outputPdfPageCount, setOutputPdfPageCount] = useState(0);
  const [sourcePdfZoom, setSourcePdfZoom] = useState(1);
  const [outputPdfZoom, setOutputPdfZoom] = useState(1);
  const [readingMaps, setReadingMaps] = useState<Record<number, PageReadingMap>>({});
  const readingMapCache = useRef(new Map<number, PageReadingMap>());
  const readingMapAbort = useRef<AbortController | null>(null);
  const readingMapIdentity = useRef<string | null>(null);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [activeFlowOrigin, setActiveFlowOrigin] = useState<"source" | "translation" | null>(null);
  const [pdfTextSelection, setPdfTextSelection] = useState<PdfTextSelection | null>(null);
  const [selectionTranslation, setSelectionTranslation] = useState<SelectionTranslationResult | null>(null);
  const [selectionTranslationBusy, setSelectionTranslationBusy] = useState(false);
  const [selectionTranslationError, setSelectionTranslationError] = useState("");
  const [error, setError] = useState("");
  const [sidebarSize, setSidebarSize] = useStoredPercent("papertrans-sidebar-size", 46);
  const [sourceSize, setSourceSize] = useStoredPercent("papertrans-source-size", 60);
  const [leftTextSize, setLeftTextSize] = useStoredPercent("papertrans-left-text-size", 22);
  const [rightTextSize, setRightTextSize] = useStoredPercent("papertrans-right-text-size", 22);
  const [pageSync, setPageSync] = useStoredBoolean("papertrans-page-sync", true);
  const [zoomSync, setZoomSync] = useStoredBoolean("papertrans-zoom-sync", true);
  const [exitOnClose, setExitOnClose] = useStoredBoolean("papertrans-exit-on-close", false);
  const [theme, setTheme] = useStoredString("papertrans-theme", "light") as [AppTheme, (value: AppTheme) => void];
  const [settingsCollapsed, setSettingsCollapsed] = useState(false);
  const [leftTextCollapsed, setLeftTextCollapsed] = useState(false);
  const [rightTextCollapsed, setRightTextCollapsed] = useState(false);
  const [windowMaximized, setWindowMaximized] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const leftColumn = useRef<HTMLDivElement>(null);
  const rightColumn = useRef<HTMLDivElement>(null);
  const leftLower = useRef<HTMLDivElement>(null);
  const textTranslationAbort = useRef<AbortController | null>(null);
  const selectionTranslationAbort = useRef<AbortController | null>(null);
  const currentProviderConfig = providerConfigs[provider] ?? providerConfigs.mock;
  const apiKey = currentProviderConfig.apiKey;
  const model = currentProviderConfig.model;
  const baseUrl = currentProviderConfig.baseUrl;

  useEffect(() => {
    void setDesktopExitOnClose(exitOnClose);
  }, [exitOnClose]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    void setDesktopTheme(theme);
  }, [theme]);

  const updateProviderConfig = (providerName: ProviderName, patch: Partial<ProviderSessionConfig>) => {
    setProviderConfigs((current) => ({
      ...current,
      [providerName]: { ...current[providerName], ...patch },
    }));
  };

  useEffect(() => {
    loadDesktopSession()
      .then((session) => {
        if (session) {
          configureDesktopApi(session.apiBase, session.sessionToken);
          void loadDesktopProviderConfigs()
            .then((storedConfigs) => {
              setProviderConfigs((current) => {
                const next = { ...current };
                storedConfigs.forEach((stored) => {
                  next[stored.provider] = {
                    apiKey: stored.apiKey,
                    model: stored.model,
                    baseUrl: stored.baseUrl,
                  };
                });
                return next;
              });
              setProviderConfigError("");
            })
            .catch(() => setProviderConfigError("无法读取 Windows 凭据管理器中的翻译服务配置"));
        }
        return loadSystemInfo();
      })
      .then((info) => {
        setSystem(info);
        setProviderConfigs((current) => {
          const next = { ...current };
          info.providers.forEach((item) => {
            if (!next[item.name].model && item.defaultModel) {
              next[item.name] = { ...next[item.name], model: item.defaultModel };
            }
          });
          return next;
        });
        if (window.localStorage.getItem("papertrans-output-directory") === null) {
          setOutputDir(info.defaultOutputDir);
        }
        return Promise.allSettled([loadLibraryTasks(), loadStorageInfo()]);
      })
      .then(([tasksResult, storageResult]) => {
        if (tasksResult.status === "fulfilled") setLibraryTasks(tasksResult.value);
        else setLibraryError(tasksResult.reason instanceof Error ? tasksResult.reason.message : "本地任务读取失败");
        if (storageResult.status === "fulfilled") setStorage(storageResult.value);
        else setStorageError(storageResult.reason instanceof Error ? storageResult.reason.message : "本地存储统计失败");
      })
      .catch((reason) => setLibraryError(reason instanceof Error ? reason.message : "本地服务暂时不可用"))
      .finally(() => setLibraryLoading(false));
  }, []);

  useEffect(() => () => {
    textTranslationAbort.current?.abort();
    selectionTranslationAbort.current?.abort();
  }, []);

  useEffect(() => {
    setSourcePdfPage(1);
    setOutputPdfPage(1);
    setSourcePdfPageCount(source?.pageCount ?? 0);
    setOutputPdfPageCount(source?.pageCount ?? 0);
    setSourcePdfZoom(1);
    setOutputPdfZoom(1);
    setActiveFlowId(null);
    setActiveFlowOrigin(null);
    setPdfTextSelection(null);
    selectionTranslationAbort.current?.abort();
    selectionTranslationAbort.current = null;
    setSelectionTranslation(null);
    setSelectionTranslationBusy(false);
    setSelectionTranslationError("");
  }, [source?.id]);

  useEffect(() => {
    let unlisten: () => void = () => undefined;
    void watchDesktopMaximized(setWindowMaximized).then((cleanup) => { unlisten = cleanup; });
    return () => unlisten();
  }, []);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      loadJob(job.id).then(setJob).catch((reason) => setError(reason.message));
    }, 900);
    return () => window.clearInterval(timer);
  }, [job]);

  useEffect(() => {
    if (job && ["completed", "review", "failed"].includes(job.status)) {
      loadLibraryTasks().then(setLibraryTasks).catch(() => undefined);
    }
  }, [job?.status]);

  useEffect(() => {
    const liveJobId = job?.status === "completed" && job.outputAvailable ? job.id : null;
    const restoredTaskId = restoredPdfTask?.kind === "pdf" && restoredPdfTask.outputPdf ? restoredPdfTask.id : null;
    const identity = restoredTaskId ? `library:${restoredTaskId}` : liveJobId ? `job:${liveJobId}` : null;
    if (readingMapIdentity.current !== identity) {
      readingMapAbort.current?.abort();
      readingMapAbort.current = null;
      readingMapIdentity.current = identity;
      readingMapCache.current.clear();
      setReadingMaps({});
    }
    if (!identity) return;

    const pages = new Set([
      ...boundedReadingMapPages(sourcePdfPage, sourcePdfPageCount, 2),
      ...boundedReadingMapPages(outputPdfPage, outputPdfPageCount, 2),
    ]);
    const retained = new Map(
      [...readingMapCache.current].filter(([page]) => pages.has(page)),
    );
    readingMapCache.current = retained;
    setReadingMaps(readingMapRecord(retained));
    const missingPages = [...pages].filter((page) => !retained.has(page));
    if (missingPages.length === 0) return;

    const controller = new AbortController();
    readingMapAbort.current?.abort();
    readingMapAbort.current = controller;
    const loader = restoredTaskId
      ? (page: number) => loadLibraryReadingMap(restoredTaskId, page, controller.signal)
      : (page: number) => loadReadingMap(liveJobId as string, page, controller.signal);
    Promise.all(missingPages.map(async (page) => {
      try {
        const mapping = await loader(page);
        if (controller.signal.aborted || readingMapIdentity.current !== identity || !pages.has(page)) return;
        const next = new Map(readingMapCache.current);
        next.set(page, mapping);
        readingMapCache.current = next;
        setReadingMaps(readingMapRecord(next));
      } catch {
        // A cancelled or unavailable adjacent page must not discard maps that already loaded.
      }
    }))
      .finally(() => {
        if (readingMapAbort.current === controller) readingMapAbort.current = null;
      });
    return () => controller.abort();
  }, [job?.id, job?.outputAvailable, job?.status, outputPdfPage, outputPdfPageCount, restoredPdfTask?.id, restoredPdfTask?.outputPdf, sourcePdfPage, sourcePdfPageCount]);

  const busy = job ? ["queued", "running"].includes(job.status) : false;
  const providerReady = provider === "mock" || Boolean(apiKey);
  const compatibleReady = provider !== "compatible" || Boolean(model && baseUrl);
  const canStart = useMemo(() => Boolean(
    source
    && outputDir
    && providerReady
    && compatibleReady,
  ), [source, outputDir, providerReady, compatibleReady]);
  const canTranslateText = Boolean(
    textSource.trim()
    && textSource.length <= MAX_TEXT_TRANSLATION_CHARS
    && providerReady
    && compatibleReady
    && !busy
  );
  const providerLabel = system.providers.find((item) => item.name === provider)?.label ?? provider;

  const resetSelectionTranslation = () => {
    selectionTranslationAbort.current?.abort();
    selectionTranslationAbort.current = null;
    setSelectionTranslation(null);
    setSelectionTranslationBusy(false);
    setSelectionTranslationError("");
  };

  const clearPdfLink = () => {
    resetSelectionTranslation();
    setActiveFlowId(null);
    setActiveFlowOrigin(null);
    setPdfTextSelection(null);
  };

  const replaceSource = (next: SourceDocument | null) => {
    if (source && source.id !== next?.id) void releaseSource(source.id).catch(() => undefined);
    setSource(next);
  };

  const changeSourcePage = (page: number) => {
    const next = clampPage(page, sourcePdfPageCount);
    setSourcePdfPage(next);
    if (pageSync) setOutputPdfPage(clampPage(next, outputPdfPageCount));
    clearPdfLink();
  };

  const changeOutputPage = (page: number) => {
    const next = clampPage(page, outputPdfPageCount);
    setOutputPdfPage(next);
    if (pageSync) setSourcePdfPage(clampPage(next, sourcePdfPageCount));
    clearPdfLink();
  };

  const changeSourceZoom = (zoom: number) => {
    if (pdfTextSelection?.side === "source") clearPdfLink();
    setSourcePdfZoom(zoom);
    if (zoomSync) setOutputPdfZoom(zoom);
  };

  const changeOutputZoom = (zoom: number) => {
    if (pdfTextSelection?.side === "translation") clearPdfLink();
    setOutputPdfZoom(zoom);
    if (zoomSync) setSourcePdfZoom(zoom);
  };

  const changePageSync = (enabled: boolean) => {
    setPageSync(enabled);
    if (enabled) setOutputPdfPage(clampPage(sourcePdfPage, outputPdfPageCount));
    clearPdfLink();
  };

  const changeZoomSync = (enabled: boolean) => {
    setZoomSync(enabled);
    if (enabled) setOutputPdfZoom(sourcePdfZoom);
  };

  const acceptFile = async (file: File) => {
    setError("");
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件"); return;
    }
    try {
      replaceSource(await uploadPdf(file));
      setJob(null);
      setRestoredPdfTask(null);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "PDF 导入失败"); }
  };

  const pickPdf = async () => {
    if (isTauriDesktop()) {
      try {
        const picked = await pickDesktopPdf();
        if (picked) {
          replaceSource(await registerSource(picked));
          setJob(null);
          setRestoredPdfTask(null);
        }
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "PDF 导入失败");
      }
    } else fileInput.current?.click();
  };

  const pickOutput = async () => {
    const picked = await pickDesktopDirectory();
    if (picked) setOutputDir(picked);
  };

  const run = async () => {
    if (!source) return;
    setError("");
    try {
      setRestoredPdfTask(null);
      setJob(await startJob({
        sourcePath: source.path,
        outputDir,
        provider,
        apiKey: apiKey || null,
        model: model || null,
        baseUrl: baseUrl || null,
        ocrEnabled,
        ocrModelDir: system.ocr.modelDir,
        targetLanguage,
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "任务启动失败"); }
  };

  const updateTextSource = (value: string) => {
    textTranslationAbort.current?.abort();
    textTranslationAbort.current = null;
    setTextTranslationBusy(false);
    setTextTranslationError("");
    setTextTranslation("");
    setTextSource(value);
    setRestoredTextTaskId(null);
  };

  const runTextTranslation = async () => {
    if (!canTranslateText || textTranslationBusy) return;
    const controller = new AbortController();
    textTranslationAbort.current?.abort();
    textTranslationAbort.current = controller;
    setTextTranslationBusy(true);
    setTextTranslationError("");
    try {
      const result = await translateText({
        text: textSource,
        provider,
        apiKey: apiKey || null,
        model: model || null,
        baseUrl: baseUrl || null,
        sourceLanguage: "auto",
        targetLanguage,
      }, controller.signal);
      if (textTranslationAbort.current === controller) {
        setTextTranslation(result.translation);
        setRestoredTextTaskId(result.task.id);
        setLibraryTasks((current) => [result.task, ...current.filter((task) => task.id !== result.task.id)]);
      }
    } catch (reason) {
      if (controller.signal.aborted) return;
      setTextTranslationError(reason instanceof Error ? reason.message : "文本翻译失败");
    } finally {
      if (textTranslationAbort.current === controller) {
        textTranslationAbort.current = null;
        setTextTranslationBusy(false);
      }
    }
  };

  const runSelectionTranslation = async () => {
    if (!pdfTextSelection || pdfTextSelection.side !== "source" || selectionTranslationBusy) return;
    if (!providerReady || !compatibleReady) {
      setSelectionTranslation(null);
      setSelectionTranslationError("请先在翻译设置中完成服务配置");
      return;
    }
    const controller = new AbortController();
    selectionTranslationAbort.current?.abort();
    selectionTranslationAbort.current = controller;
    setSelectionTranslation(null);
    setSelectionTranslationBusy(true);
    setSelectionTranslationError("");
    try {
      const result = await translateSelection({
        text: pdfTextSelection.text,
        provider,
        apiKey: apiKey || null,
        model: model || null,
        baseUrl: baseUrl || null,
        sourceLanguage: "auto",
        targetLanguage,
      }, controller.signal);
      if (selectionTranslationAbort.current === controller) setSelectionTranslation(result);
    } catch (reason) {
      if (controller.signal.aborted) return;
      setSelectionTranslationError(reason instanceof Error ? reason.message : "所选文本翻译失败");
    } finally {
      if (selectionTranslationAbort.current === controller) {
        selectionTranslationAbort.current = null;
        setSelectionTranslationBusy(false);
      }
    }
  };

  const resizeSidebar = (deltaX: number) => {
    const bounds = workspace.current?.getBoundingClientRect();
    if (!bounds) return;
    setSidebarSize((current) => clamp(current + (deltaX / bounds.width) * 100, 36, 56));
  };

  const adjustTextSize = (
    current: number,
    deltaPercent: number,
    collapsed: boolean,
    setSize: Dispatch<SetStateAction<number>>,
    setCollapsed: Dispatch<SetStateAction<boolean>>,
  ) => {
    if (collapsed) {
      if (deltaPercent > 0) {
        setCollapsed(false);
        setSize(18);
      }
      return;
    }
    const next = clamp(current + deltaPercent, TEXT_COLLAPSE_THRESHOLD, 46);
    setSize(next);
    if (next <= TEXT_COLLAPSE_THRESHOLD && deltaPercent < 0) setCollapsed(true);
  };

  const resizeLeftText = (deltaY: number) => {
    const bounds = leftColumn.current?.getBoundingClientRect();
    if (!bounds) return;
    adjustTextSize(leftTextSize, (deltaY / bounds.height) * 100, leftTextCollapsed, setLeftTextSize, setLeftTextCollapsed);
  };

  const resizeRightText = (deltaY: number) => {
    const bounds = rightColumn.current?.getBoundingClientRect();
    if (!bounds) return;
    adjustTextSize(rightTextSize, (deltaY / bounds.height) * 100, rightTextCollapsed, setRightTextSize, setRightTextCollapsed);
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
    const bounds = leftLower.current?.getBoundingClientRect();
    if (!bounds) return;
    adjustSourceSize((deltaY / bounds.height) * 100);
  };

  const clearSource = () => {
    replaceSource(null);
    setJob(null);
    setRestoredPdfTask(null);
  };

  const changeView = (nextView: View) => {
    if (nextView === view) return;
    setConfiguringProvider(null);
    setViewDirection(VIEW_ORDER[nextView] > VIEW_ORDER[view] ? "forward" : "backward");
    setView(nextView);
    if (nextView === "library") {
      setLibraryLoading(true);
      setLibraryError("");
      loadLibraryTasks()
        .then(setLibraryTasks)
        .catch((reason) => setLibraryError(reason instanceof Error ? reason.message : "本地任务读取失败"))
        .finally(() => setLibraryLoading(false));
    } else if (nextView === "settings") {
      setStorageError("");
      loadStorageInfo()
        .then(setStorage)
        .catch((reason) => setStorageError(reason instanceof Error ? reason.message : "本地存储统计失败"));
    }
  };

  const restoreLibraryTask = async (task: LibraryTaskSummary) => {
    try {
      const detail = await loadLibraryTask(task.id);
      if (detail.kind !== "text" || detail.sourceText === undefined || detail.translation === undefined) return;
      textTranslationAbort.current?.abort();
      setTextSource(detail.sourceText);
      setTextTranslation(detail.translation);
      setTextTranslationError("");
      setTextTranslationBusy(false);
      setRestoredTextTaskId(detail.id);
      setProvider(detail.provider);
      changeView("translate");
    } catch (reason) {
      setLibraryError(reason instanceof Error ? reason.message : "文本任务恢复失败");
    }
  };

  const restoreLibraryPdfTask = async (task: LibraryTaskSummary) => {
    try {
      const detail = await loadLibraryTask(task.id);
      if (detail.kind !== "pdf" || detail.status !== "completed" || !detail.sourcePath || !detail.outputPdf) {
        throw new Error("该 PDF 任务尚未生成可恢复的译文");
      }
      const restoredSource = await registerSource(detail.sourcePath);
      replaceSource(restoredSource);
      setJob(null);
      setRestoredPdfTask(detail);
      setProvider(detail.provider);
      clearPdfLink();
      changeView("translate");
    } catch (reason) {
      setLibraryError(reason instanceof Error ? reason.message : "PDF 任务恢复失败");
    }
  };

  const openStoredTask = async (task: LibraryTaskSummary) => {
    try { await openLibraryTask(task.id); }
    catch (reason) { setLibraryError(reason instanceof Error ? reason.message : "任务目录打开失败"); }
  };

  const requestConfirmation = (action: PendingConfirmation) => {
    setConfirmationError("");
    setPendingConfirmation(action);
  };

  const performConfirmedAction = async () => {
    const action = pendingConfirmation;
    if (!action || confirmationBusy) return;
    setConfirmationBusy(true);
    setConfirmationError("");
    try {
      if (action.kind === "delete-task") {
        await deleteLibraryTask(action.task.id);
        setLibraryTasks((current) => current.filter((task) => task.id !== action.task.id));
        if (restoredTextTaskId === action.task.id) {
          textTranslationAbort.current?.abort();
          setRestoredTextTaskId(null);
          setTextSource("");
          setTextTranslation("");
          setTextTranslationError("");
          setTextTranslationBusy(false);
        }
        if (restoredPdfTask?.id === action.task.id) {
          setRestoredPdfTask(null);
          clearPdfLink();
        }
        if (job?.id === action.task.id) {
          setJob(null);
          clearPdfLink();
        }
      } else if (action.kind === "clear-cache") {
        const result = await clearTranslationCache();
        setStorage(result.storage);
      } else {
        const result = await clearTemporaryUploads();
        setStorage(result.storage);
      }
      setPendingConfirmation(null);
    } catch (reason) {
      setConfirmationError(reason instanceof Error ? reason.message : "操作失败，请重试");
    } finally {
      setConfirmationBusy(false);
    }
  };

  return (
    <div className={windowMaximized ? "desktop-app window-maximized" : "desktop-app"} inert={configuringProvider !== null || pendingConfirmation !== null}>
      <Header view={view} onView={changeView} maximized={windowMaximized} onMaximized={setWindowMaximized} />
      <main
        className={`translate-page view-stage view-${viewDirection} ${view === "translate" ? "view-active" : "view-preserved"}`}
        aria-hidden={view !== "translate"}
        inert={view !== "translate"}
      >
          {error && <div className="error-banner"><Icon name="error" size={18} />{error}<button onClick={() => setError("")}><Icon name="close" size={17} /></button></div>}
          <div className="workspace-grid" ref={workspace} style={{ "--sidebar-size": `${sidebarSize}%` } as CSSProperties}>
            <div
              className={leftTextCollapsed ? "workspace-column left-column text-collapsed" : "workspace-column left-column"}
              ref={leftColumn}
              style={{ "--text-dock-size": `${leftTextSize}%` } as CSSProperties}
            >
              <TextSourcePanel value={textSource} onChange={updateTextSource} onTranslate={() => void runTextTranslation()}
                canTranslate={canTranslateText} busy={textTranslationBusy} collapsed={leftTextCollapsed}
                onExpand={() => { setLeftTextCollapsed(false); setLeftTextSize(22); }} />
              <ResizeHandle orientation="horizontal" label="调整文本原文与 PDF 区域高度" onDrag={resizeLeftText} onNudge={(delta) => adjustTextSize(leftTextSize, delta, leftTextCollapsed, setLeftTextSize, setLeftTextCollapsed)} />
              <div className={settingsCollapsed ? "left-lower settings-collapsed" : "left-lower"} ref={leftLower} style={{ "--source-size": `${sourceSize}%` } as CSSProperties}>
                {source ? <SourcePanel source={source} onPick={pickPdf} onDrop={acceptFile} onClear={clearSource}
                  page={sourcePdfPage} zoom={sourcePdfZoom} onPage={changeSourcePage}
                  onPageCount={setSourcePdfPageCount} onZoom={changeSourceZoom} readingMaps={readingMaps}
                  activeFlowId={activeFlowId} selectionOrigin={activeFlowOrigin}
                  textSelection={pdfTextSelection}
                  selectionTranslation={selectionTranslation} selectionTranslationBusy={selectionTranslationBusy}
                  selectionTranslationError={selectionTranslationError}
                  onTranslateSelection={() => void runSelectionTranslation()}
                  onDismissSelectionTranslation={resetSelectionTranslation}
                  onTextSelect={(flowId, selectedText) => {
                    resetSelectionTranslation();
                    setActiveFlowId(null);
                    setActiveFlowOrigin(null);
                    setPdfTextSelection({ flowId, side: "source", text: selectedText });
                  }}
                  onFlowSelect={(flowId, targetPage) => {
                    resetSelectionTranslation();
                    setActiveFlowId(flowId);
                    setActiveFlowOrigin("source");
                    setPdfTextSelection(null);
                    if (targetPage) setOutputPdfPage(clampPage(targetPage, outputPdfPageCount));
                  }}
                  onFlowClear={clearPdfLink} /> : <UploadCard onPick={pickPdf} onDrop={acceptFile} />}
                <ResizeHandle orientation="horizontal" label="调整源 PDF 与设置区域高度" onDrag={resizeSource} onNudge={adjustSourceSize} />
        <SettingsCard system={system} provider={provider} onProvider={setProvider} targetLanguage={targetLanguage} onTargetLanguage={setTargetLanguage} apiKey={apiKey} onApiKey={(value) => updateProviderConfig(provider, { apiKey: value })}
                  model={model} onModel={(value) => updateProviderConfig(provider, { model: value })} baseUrl={baseUrl} onBaseUrl={(value) => updateProviderConfig(provider, { baseUrl: value })} ocrEnabled={ocrEnabled} onOcr={setOcrEnabled}
                  outputDir={outputDir} onOutput={setOutputDir} onPickOutput={pickOutput} canStart={canStart && !textTranslationBusy} onStart={run} busy={busy}
                  collapsed={settingsCollapsed} onExpand={() => { setSettingsCollapsed(false); setSourceSize(60); }} />
              </div>
            </div>
            <ResizeHandle orientation="vertical" label="调整源文件与译文区域宽度" onDrag={resizeSidebar} onNudge={(delta) => setSidebarSize(clamp(sidebarSize + delta, 36, 56))} />
            <div
              className={rightTextCollapsed ? "workspace-column right-column text-collapsed" : "workspace-column right-column"}
              ref={rightColumn}
              style={{ "--text-dock-size": `${rightTextSize}%` } as CSSProperties}
            >
              <TextOutputPanel source={textSource} translation={textTranslation} busy={textTranslationBusy}
                error={textTranslationError} providerLabel={providerLabel} collapsed={rightTextCollapsed}
                onExpand={() => { setRightTextCollapsed(false); setRightTextSize(22); }} />
              <ResizeHandle orientation="horizontal" label="调整文本译文与翻译 PDF 区域高度" onDrag={resizeRightText} onNudge={(delta) => adjustTextSize(rightTextSize, delta, rightTextCollapsed, setRightTextSize, setRightTextCollapsed)} />
              <ReadyPanel source={source} job={job} restoredTask={restoredPdfTask} page={outputPdfPage} zoom={outputPdfZoom}
                onPage={changeOutputPage} onPageCount={setOutputPdfPageCount} onZoom={changeOutputZoom}
                readingMaps={readingMaps} activeFlowId={activeFlowId} selectionOrigin={activeFlowOrigin}
                textSelection={pdfTextSelection}
                onFlowSelect={(flowId, targetPage) => {
                  resetSelectionTranslation();
                  setActiveFlowId(flowId);
                  setActiveFlowOrigin("translation");
                  setPdfTextSelection(null);
                  if (targetPage) setSourcePdfPage(clampPage(targetPage, sourcePdfPageCount));
                }}
                onFlowClear={clearPdfLink} />
            </div>
          </div>
          <input ref={fileInput} hidden type="file" accept="application/pdf,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.[0]; if (file) acceptFile(file);
          }} />
      </main>
      {view === "library" && <LibraryPage direction={viewDirection} tasks={libraryTasks} loading={libraryLoading} error={libraryError}
        onRestoreText={(task) => void restoreLibraryTask(task)}
        onRestorePdf={(task) => void restoreLibraryPdfTask(task)} onOpen={(task) => void openStoredTask(task)}
        onDelete={(task) => requestConfirmation({ kind: "delete-task", task })} />}
      {view === "settings" && <SettingsPage system={system} direction={viewDirection}
        providerConfigs={providerConfigs} providerConfigError={providerConfigError} onConfigure={setConfiguringProvider}
        exitOnClose={exitOnClose} onExitOnClose={setExitOnClose} theme={theme} onTheme={setTheme}
        outputDir={outputDir} onOutput={setOutputDir} onPickOutput={() => void pickOutput()} onResetOutput={() => setOutputDir(system.defaultOutputDir)}
        pageSync={pageSync} onPageSync={changePageSync} zoomSync={zoomSync} onZoomSync={changeZoomSync}
        storage={storage} storageError={storageError}
        onClearCache={() => requestConfirmation({ kind: "clear-cache" })}
        onClearUploads={() => requestConfirmation({ kind: "clear-uploads" })} />}
      {configuringProvider && (() => {
        const descriptor = system.providers.find((item) => item.name === configuringProvider);
        return descriptor ? (
          <ProviderConfigDialog
            key={configuringProvider}
            provider={descriptor}
            config={providerConfigs[configuringProvider]}
            onCancel={() => setConfiguringProvider(null)}
            onSave={async (config) => {
              if (configuringProvider === "mock") return;
              await saveDesktopProviderConfig({ provider: configuringProvider, ...config });
              updateProviderConfig(configuringProvider, config);
              setProviderConfigError("");
              setConfiguringProvider(null);
            }}
          />
        ) : null;
      })()}
      {pendingConfirmation && <ConfirmationDialog
        action={pendingConfirmation}
        busy={confirmationBusy}
        error={confirmationError}
        onCancel={() => { if (!confirmationBusy) setPendingConfirmation(null); }}
        onConfirm={() => void performConfirmedAction()}
      />}
    </div>
  );
}

function formatBytes(value: number): string {
  if (value <= 0) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return minutes > 0 ? `${minutes} 分 ${String(remainingSeconds).padStart(2, "0")} 秒` : `${remainingSeconds} 秒`;
}

function formatLibraryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

function libraryStatusLabel(status: LibraryTaskSummary["status"]): string {
  return { queued: "等待中", running: "处理中", completed: "已完成", review: "待检查", failed: "失败" }[status];
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Number(value.toFixed(2))));
}

function clampPage(value: number, count: number): number {
  return Math.min(Math.max(1, value), Math.max(1, count));
}

function boundedReadingMapPages(page: number, pageCount: number, radius: number): number[] {
  if (pageCount <= 0) return [];
  const current = clampPage(page, pageCount);
  const start = Math.max(1, current - Math.max(0, radius));
  const end = Math.min(pageCount, current + Math.max(0, radius));
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function readingMapRecord(cache: Map<number, PageReadingMap>): Record<number, PageReadingMap> {
  return Object.fromEntries(cache) as Record<number, PageReadingMap>;
}
