import type { JobState, LibraryTaskDetail, LibraryTaskSummary, PageReadingMap, SelectionTranslationResult, SourceDocument, StorageCleanupResult, StorageInfo, SystemInfo, TextTranslationResult } from "./types";

const query = new URLSearchParams(window.location.search);
const queryToken = query.get("session");
if (queryToken) sessionStorage.setItem("papertrans-session", queryToken);
let sessionToken = sessionStorage.getItem("papertrans-session");
let apiBase = "";

export function configureDesktopApi(base: string, token: string): void {
  apiBase = base.replace(/\/$/, "");
  sessionToken = token;
}

function requestUrl(path: string): string {
  return apiBase ? `${apiBase}${path}` : path;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (sessionToken) headers.set("X-PaperTrans-Token", sessionToken);
  const response = await fetch(requestUrl(path), { ...init, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "本地服务暂时不可用");
  }
  return response.json() as Promise<T>;
}

export async function loadSystemInfo(): Promise<SystemInfo> {
  return api<SystemInfo>("/api/system");
}

export async function uploadPdf(file: File): Promise<SourceDocument> {
  const body = new FormData();
  body.append("file", file);
  return api<SourceDocument>("/api/uploads", { method: "POST", body });
}

export async function registerSource(path: string): Promise<SourceDocument> {
  return api<SourceDocument>("/api/sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}

export async function listProviderModels(payload: Record<string, unknown>): Promise<string[]> {
  const result = await api<{ models: string[] }>("/api/provider-models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return result.models;
}

export async function startJob(payload: Record<string, unknown>): Promise<JobState> {
  return api<JobState>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function translateText(
  payload: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<TextTranslationResult> {
  return api<TextTranslationResult>("/api/text-translations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export async function translateSelection(
  payload: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<SelectionTranslationResult> {
  return api<SelectionTranslationResult>("/api/selection-translations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export async function loadJob(jobId: string): Promise<JobState> {
  return api<JobState>(`/api/jobs/${jobId}`);
}

export async function loadReadingMap(
  jobId: string,
  pageNumber: number,
  signal?: AbortSignal,
): Promise<PageReadingMap> {
  return api<PageReadingMap>(`/api/jobs/${jobId}/reading-map/${pageNumber}`, { signal });
}

export async function loadLibraryTasks(): Promise<LibraryTaskSummary[]> {
  const result = await api<{ tasks: LibraryTaskSummary[] }>("/api/library/tasks");
  return result.tasks;
}

export async function loadLibraryTask(taskId: string): Promise<LibraryTaskDetail> {
  return api<LibraryTaskDetail>(`/api/library/tasks/${taskId}`);
}

export async function deleteLibraryTask(taskId: string): Promise<boolean> {
  const result = await api<{ deleted: boolean }>(`/api/library/tasks/${taskId}`, {
    method: "DELETE",
  });
  return result.deleted;
}

export async function loadLibraryReadingMap(
  taskId: string,
  pageNumber: number,
  signal?: AbortSignal,
): Promise<PageReadingMap> {
  return api<PageReadingMap>(`/api/library/tasks/${taskId}/reading-map/${pageNumber}`, { signal });
}

export async function openLibraryTask(taskId: string): Promise<boolean> {
  const result = await api<{ opened: boolean }>(`/api/library/tasks/${taskId}/open`, {
    method: "POST",
  });
  return result.opened;
}

export async function loadStorageInfo(): Promise<StorageInfo> {
  return api<StorageInfo>("/api/storage");
}

export async function clearTranslationCache(): Promise<StorageCleanupResult> {
  return api<StorageCleanupResult>("/api/storage/cache/clear", { method: "POST" });
}

export async function clearTemporaryUploads(): Promise<StorageCleanupResult> {
  return api<StorageCleanupResult>("/api/storage/uploads/clear", { method: "POST" });
}

export async function releaseSource(sourceId: string): Promise<boolean> {
  const result = await api<{ released: boolean }>(`/api/sources/${sourceId}`, {
    method: "DELETE",
  });
  return result.released;
}

export function artifactUrl(jobId: string, kind: "source" | "output"): string {
  const token = sessionToken ? `?session=${encodeURIComponent(sessionToken)}` : "";
  return requestUrl(`/api/jobs/${jobId}/${kind}${token}`);
}

export function libraryArtifactUrl(taskId: string, kind: "source" | "output"): string {
  const token = sessionToken ? `?session=${encodeURIComponent(sessionToken)}` : "";
  return requestUrl(`/api/library/tasks/${taskId}/${kind}${token}`);
}

export function sourceUrl(sourceId: string): string {
  const token = sessionToken ? `?session=${encodeURIComponent(sessionToken)}` : "";
  return requestUrl(`/api/sources/${sourceId}${token}`);
}

export async function openJobOutput(jobId: string): Promise<boolean> {
  const result = await api<{ opened: boolean }>(`/api/jobs/${jobId}/open`, {
    method: "POST",
  });
  return result.opened;
}
