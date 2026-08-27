fn main() {
    // Tauri embeds this ICO into the Windows executable.  Track it explicitly so a
    // regenerated brand asset cannot leave the desktop/taskbar shortcut pointing at
    // an executable built with an earlier icon while the runtime tray uses the new one.
    println!("cargo:rerun-if-changed=icons/icon.ico");
    println!("cargo:rerun-if-changed=tauri.conf.json");
    tauri_build::build()
}
