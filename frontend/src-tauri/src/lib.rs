use keyring::v1::{Entry, Error as KeyringError};
use serde::{Deserialize, Serialize};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, RunEvent, WindowEvent,
};

#[cfg(debug_assertions)]
use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
};
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[cfg(all(not(debug_assertions), target_os = "windows"))]
use windows_sys::Win32::{
    Foundation::{CloseHandle, HANDLE},
    System::{
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
            SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        },
        Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE},
    },
};

#[cfg(all(debug_assertions, target_os = "windows"))]
use std::os::windows::process::CommandExt;

#[cfg(all(debug_assertions, target_os = "windows"))]
const CREATE_NO_WINDOW: u32 = 0x08000000;
const CREDENTIAL_SERVICE: &str = "PaperTrans/provider-config";
const CREDENTIAL_PROVIDERS: [&str; 4] = ["deepseek", "kimi", "zhipu", "compatible"];

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopSession {
    api_base: String,
    session_token: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct StoredProviderConfig {
    provider: String,
    api_key: String,
    model: String,
    base_url: String,
}

enum BackendProcessHandle {
    #[cfg(debug_assertions)]
    Development(Child),
    #[cfg(not(debug_assertions))]
    Sidecar {
        child: CommandChild,
        #[cfg(target_os = "windows")]
        _job: BackendJob,
    },
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
struct BackendJob(usize);

#[cfg(all(not(debug_assertions), target_os = "windows"))]
impl Drop for BackendJob {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.0 as HANDLE);
        }
    }
}

impl BackendProcessHandle {
    fn stop(self) {
        match self {
            #[cfg(debug_assertions)]
            Self::Development(mut child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            #[cfg(not(debug_assertions))]
            Self::Sidecar { child, .. } => {
                let _ = child.kill();
            }
        }
    }
}

struct BackendProcess(Mutex<Option<BackendProcessHandle>>);
struct CloseBehavior(Mutex<bool>);

#[tauri::command]
fn desktop_session(state: tauri::State<'_, DesktopSession>) -> DesktopSession {
    state.inner().clone()
}

#[tauri::command]
fn load_provider_configs() -> Result<Vec<StoredProviderConfig>, String> {
    let mut configs = Vec::new();
    for provider in CREDENTIAL_PROVIDERS {
        let entry = credential_entry(provider)?;
        match entry.get_password() {
            Ok(payload) => {
                let mut config: StoredProviderConfig = serde_json::from_str(&payload)
                    .map_err(|_| "保存的翻译服务配置无法读取，请重新配置。".to_string())?;
                config.provider = provider.to_string();
                configs.push(config);
            }
            Err(KeyringError::NoEntry) => {}
            Err(_) => return Err("无法访问 Windows 凭据管理器。".to_string()),
        }
    }
    Ok(configs)
}

#[tauri::command]
fn save_provider_config(config: StoredProviderConfig) -> Result<(), String> {
    validate_provider_config(&config)?;
    let entry = credential_entry(&config.provider)?;
    let payload =
        serde_json::to_string(&config).map_err(|_| "无法准备翻译服务配置。".to_string())?;
    entry
        .set_password(&payload)
        .map_err(|_| "无法将翻译服务配置保存到 Windows 凭据管理器。".to_string())
}

#[tauri::command]
fn set_exit_on_close(enabled: bool, state: tauri::State<'_, CloseBehavior>) -> Result<(), String> {
    let mut exit_on_close = state
        .0
        .lock()
        .map_err(|_| "无法更新关闭行为。".to_string())?;
    *exit_on_close = enabled;
    Ok(())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn credential_entry(provider: &str) -> Result<Entry, String> {
    if !CREDENTIAL_PROVIDERS.contains(&provider) {
        return Err("不支持的翻译服务配置。".to_string());
    }
    Entry::new(CREDENTIAL_SERVICE, provider)
        .map_err(|_| "无法访问 Windows 凭据管理器。".to_string())
}

fn validate_provider_config(config: &StoredProviderConfig) -> Result<(), String> {
    if !CREDENTIAL_PROVIDERS.contains(&config.provider.as_str()) {
        return Err("不支持的翻译服务配置。".to_string());
    }
    if config.api_key.trim().is_empty() {
        return Err("API Key 不能为空。".to_string());
    }
    if config.model.trim().is_empty() {
        return Err("模型名称不能为空。".to_string());
    }
    if config.provider == "compatible"
        && !(config.base_url.starts_with("https://") || config.base_url.starts_with("http://"))
    {
        return Err("兼容接口必须使用 HTTP(S) API 地址。".to_string());
    }
    Ok(())
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            desktop_session,
            load_provider_configs,
            save_provider_config,
            set_exit_on_close
        ])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let exit_on_close = window
                    .app_handle()
                    .state::<CloseBehavior>()
                    .0
                    .lock()
                    .map(|value| *value)
                    .unwrap_or(false);
                if !exit_on_close {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            let port = available_port()?;
            let token = uuid::Uuid::new_v4().simple().to_string();
            let child = spawn_backend(app.handle(), port, &token)?;
            // The session address and token are known immediately; publish them now so the
            // window can paint and the frontend can start polling. The local FastAPI sidecar
            // (bundled as a self-extracting one-file binary) may take several seconds to begin
            // listening, so wait for readiness on a background thread instead of blocking the
            // main thread — otherwise the webview stays black until the backend is up.
            app.manage(DesktopSession {
                api_base: format!("http://127.0.0.1:{port}"),
                session_token: token,
            });
            app.manage(BackendProcess(Mutex::new(Some(child))));
            app.manage(CloseBehavior(Mutex::new(false)));
            std::thread::spawn(move || {
                let _ = wait_for_backend(port, Duration::from_secs(60));
            });

            let show_item =
                MenuItem::with_id(app, "tray-show", "显示 PaperTrans", true, None::<&str>)?;
            let quit_item =
                MenuItem::with_id(app, "tray-quit", "退出 PaperTrans", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_item, &quit_item])?;
            let tray_icon = TrayIconBuilder::with_id("papertrans-tray")
                .icon(
                    app.default_window_icon()
                        .cloned()
                        .ok_or("PaperTrans tray icon is unavailable")?,
                )
                .tooltip("PaperTrans")
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "tray-show" => show_main_window(app),
                    "tray-quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if matches!(
                        event,
                        TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        }
                    ) {
                        show_main_window(tray.app_handle());
                    }
                })
                .build(app)?;
            app.manage(tray_icon);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build PaperTrans desktop application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(process) = app_handle.try_state::<BackendProcess>() {
                if let Ok(mut guard) = process.0.lock() {
                    if let Some(child) = guard.take() {
                        child.stop();
                    }
                }
            }
        }
    });
}

#[cfg(debug_assertions)]
fn repository_root() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    Ok(manifest
        .parent()
        .and_then(Path::parent)
        .ok_or("could not resolve repository root")?
        .canonicalize()?)
}

fn available_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

fn spawn_backend(
    app: &AppHandle,
    port: u16,
    token: &str,
) -> Result<BackendProcessHandle, Box<dyn std::error::Error>> {
    #[cfg(debug_assertions)]
    {
        let _ = app;
        let repository = repository_root()?;
        return spawn_development_backend(&repository, port, token);
    }

    #[cfg(not(debug_assertions))]
    {
        let data_root = app.path().app_local_data_dir()?;
        std::fs::create_dir_all(&data_root)?;
        let ocr_model_dir = app
            .path()
            .resource_dir()?
            .join("models")
            .join("paddleocr");
        if !ocr_model_dir.is_dir() {
            return Err(format!(
                "Bundled OCR model directory is unavailable: {}",
                ocr_model_dir.display()
            )
            .into());
        }
        let port_argument = port.to_string();
        let data_root_argument = data_root.to_string_lossy().into_owned();
        let ocr_model_argument = ocr_model_dir.to_string_lossy().into_owned();
        let (_events, child) = app
            .shell()
            .sidecar("papertrans-backend")?
            .args([
                "--port",
                port_argument.as_str(),
                "--token",
                token,
                "--data-root",
                data_root_argument.as_str(),
                "--ocr-model-dir",
                ocr_model_argument.as_str(),
            ])
            .current_dir(&data_root)
            .spawn()?;
        #[cfg(target_os = "windows")]
        let job = attach_backend_job(child.pid())?;
        Ok(BackendProcessHandle::Sidecar {
            child,
            #[cfg(target_os = "windows")]
            _job: job,
        })
    }
}

#[cfg(all(not(debug_assertions), target_os = "windows"))]
fn attach_backend_job(process_id: u32) -> Result<BackendJob, Box<dyn std::error::Error>> {
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }

        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            std::ptr::addr_of!(limits).cast(),
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        ) == 0
        {
            let error = std::io::Error::last_os_error();
            let _ = CloseHandle(job);
            return Err(error.into());
        }

        let process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, process_id);
        if process.is_null() {
            let error = std::io::Error::last_os_error();
            let _ = CloseHandle(job);
            return Err(error.into());
        }
        let assigned = AssignProcessToJobObject(job, process);
        let assignment_error = std::io::Error::last_os_error();
        let _ = CloseHandle(process);
        if assigned == 0 {
            let _ = CloseHandle(job);
            return Err(assignment_error.into());
        }

        Ok(BackendJob(job as usize))
    }
}

#[cfg(debug_assertions)]
fn spawn_development_backend(
    repository: &Path,
    port: u16,
    token: &str,
) -> Result<BackendProcessHandle, Box<dyn std::error::Error>> {
    let python = repository.join(".venv").join("Scripts").join("python.exe");
    if !python.is_file() {
        return Err(format!("Python environment not found at {}", python.display()).into());
    }
    let mut command = Command::new(python);
    command
        .current_dir(repository)
        .arg("-m")
        .arg("papertrans.desktop.server")
        .arg("--port")
        .arg(port.to_string())
        .arg("--token")
        .arg(token)
        .arg("--repository")
        .arg(repository)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    command.creation_flags(CREATE_NO_WINDOW);
    Ok(BackendProcessHandle::Development(command.spawn()?))
}

fn wait_for_backend(port: u16, timeout: Duration) -> Result<(), Box<dyn std::error::Error>> {
    let address: SocketAddr = format!("127.0.0.1:{port}").parse()?;
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_ok() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(80));
    }
    Err("PaperTrans Python service did not become ready".into())
}

#[cfg(test)]
mod tests {
    use super::{validate_provider_config, StoredProviderConfig};

    fn config(provider: &str, api_key: &str, model: &str, base_url: &str) -> StoredProviderConfig {
        StoredProviderConfig {
            provider: provider.to_string(),
            api_key: api_key.to_string(),
            model: model.to_string(),
            base_url: base_url.to_string(),
        }
    }

    #[test]
    fn provider_config_validation_accepts_named_and_compatible_services() {
        assert!(
            validate_provider_config(&config("deepseek", "test-key", "deepseek-v4-flash", ""))
                .is_ok()
        );
        assert!(validate_provider_config(&config(
            "compatible",
            "test-key",
            "test-model",
            "https://api.example.com/v1"
        ))
        .is_ok());
    }

    #[test]
    fn provider_config_validation_rejects_unknown_or_incomplete_services() {
        assert!(validate_provider_config(&config("mock", "test-key", "model", "")).is_err());
        assert!(validate_provider_config(&config("kimi", "", "kimi-k2.6", "")).is_err());
        assert!(validate_provider_config(&config(
            "compatible",
            "test-key",
            "model",
            "file:///unsafe"
        ))
        .is_err());
    }
}
