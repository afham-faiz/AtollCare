// Fetch wrapper: JSON in/out, engine error shape → ApiError (toasted by callers). Types come from the engine.
import { ENGINE_URL } from "@/app/config";
import type { components } from "@/lib/api-types";

type S = components["schemas"];
export type Transfer = S["Transfer"];
export type TransferListItem = S["TransferListItem"];
export type Note = S["Note"];
export type MetaResponse = S["MetaResponse"];
export type Region = S["Region"];
export type Facility = S["Facility"];
export type TransportMode = S["TransportMode"];
export type TrendResponse = S["TrendResponse"];
export type DeteriorationForecast = S["DeteriorationForecast"];
export type Briefing = S["Briefing"];
export type Alert = S["Alert"];
export type LatestValue = S["LatestValue"];
export type News2Result = S["News2Result"];
export type VitalsRequest = S["VitalsRequest"];
export type MonitoringSource = S["MonitoringSource"];
export type TransferStatus = S["TransferStatus"];
export type DemoCase = S["DemoCase"];
export type Intervention = S["Intervention"];
export type InfraStatus = S["InfraStatus"];
export type InsightsResponse = S["InsightsResponse"];
export type BenchmarkResponse = S["BenchmarkResponse"];
export type SeedHistoryResponse = S["SeedHistoryResponse"];
export type Intake = S["Intake"];
export type Scan = S["Scan"];
export type Demographics = S["Demographics"];
export type VisualCueReport = S["VisualCueReport"];
export type CueFinding = S["CueFinding"];
export type RppgEstimates = S["RppgEstimates"];

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${ENGINE_URL}${path}`, {
      ...rest,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    });
  } catch {
    throw new ApiError("network", "Can't reach the server — check the connection", 0);
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(code, message, res.status);
  }
  return (await res.json()) as T;
}

/** A multipart upload with progress (fetch can't report upload progress): phone videos are tens of MB on a slow
 *  uplink, and the person holding the phone needs to see it going. */
export function uploadForm<T>(path: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${ENGINE_URL}${path}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError("network", "Can't reach the server — check the connection", 0));
    xhr.onload = () => {
      let body: { error?: { code?: string; message?: string } } | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) return resolve(body as T);
      reject(new ApiError(body?.error?.code ?? "http_error", body?.error?.message ?? `Request failed (${xhr.status})`, xhr.status));
    };
    xhr.send(form);
  });
}

export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const patch = <T>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const fetcher = <T>(path: string) => api<T>(path);
