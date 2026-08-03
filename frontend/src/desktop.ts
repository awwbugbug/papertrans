import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open } from "@tauri-apps/plugin-dialog";

export type DesktopSession = {
  apiBase: string;
  sessionToken: string;
};

export function isTauriDesktop(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

export async function loadDesktopSession(): Promise<DesktopSession | null> {
  if (!isTauriDesktop()) return null;
  return invoke<DesktopSession>("desktop_session");
}

export async function pickDesktopPdf(): Promise<string | null> {
  if (!isTauriDesktop()) return null;
  const selected = await open({
    directory: false,
    multiple: false,
    filters: [{ name: "PDF", extensions: ["pdf"] }],
  });
  return typeof selected === "string" ? selected : null;
}

export async function pickDesktopDirectory(): Promise<string | null> {
  if (!isTauriDesktop()) return null;
  const selected = await open({ directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}

export async function minimizeDesktopWindow(): Promise<void> {
  if (isTauriDesktop()) await getCurrentWindow().minimize();
}

export async function toggleDesktopMaximize(): Promise<boolean> {
  if (!isTauriDesktop()) return false;
  const appWindow = getCurrentWindow();
  await appWindow.toggleMaximize();
  return appWindow.isMaximized();
}

export async function closeDesktopWindow(): Promise<void> {
  if (isTauriDesktop()) await getCurrentWindow().close();
}

export async function watchDesktopMaximized(
  update: (maximized: boolean) => void,
): Promise<() => void> {
  if (!isTauriDesktop()) return () => undefined;
  const appWindow = getCurrentWindow();
  update(await appWindow.isMaximized());
  return appWindow.onResized(async () => update(await appWindow.isMaximized()));
}
