import type { JobState, SourceDocument, SystemInfo } from "./types";

const query = new URLSearchParams(window.location.search);
const queryToken = query.get("session");
if (queryToken) sessionStorage.setItem("papertrans-session", queryToken);
const sessionToken = sessionStorage.getItem("papertrans-session");

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (sessionToken) headers.set("X-PaperTrans-Token", sessionToken);
  const response = await fetch(path, { ...init, headers });
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

export async function startJob(payload: Record<string, unknown>): Promise<JobState> {
  return api<JobState>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function loadJob(jobId: string): Promise<JobState> {
  return api<JobState>(`/api/jobs/${jobId}`);
}

export function artifactUrl(jobId: string, kind: "source" | "output"): string {
  const token = sessionToken ? `?session=${encodeURIComponent(sessionToken)}` : "";
  return `/api/jobs/${jobId}/${kind}${token}`;
}
