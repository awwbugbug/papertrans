use serde::Serialize;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopSession {
    api_base: String,
    session_token: String,
}

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
fn desktop_session(state: tauri::State<'_, DesktopSession>) -> DesktopSession {
    state.inner().clone()
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![desktop_session])
        .setup(|app| {
            let repository = repository_root()?;
            let port = available_port()?;
            let token = uuid::Uuid::new_v4().simple().to_string();
            let mut child = spawn_backend(&repository, port, &token)?;
            if let Err(error) = wait_for_backend(port, Duration::from_secs(12)) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
            app.manage(DesktopSession {
                api_base: format!("http://127.0.0.1:{port}"),
                session_token: token,
            });
            app.manage(BackendProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build PaperTrans desktop application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(process) = app_handle.try_state::<BackendProcess>() {
                if let Ok(mut guard) = process.0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        }
    });
}

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
    repository: &Path,
    port: u16,
    token: &str,
) -> Result<Child, Box<dyn std::error::Error>> {
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
    Ok(command.spawn()?)
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
