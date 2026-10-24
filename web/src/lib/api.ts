// F-M7.7 fetch wrapper: JSON in/out, X-Role header, engine error shape → ApiError (toasted by callers).
import { ENGINE_URL } from "@/app/config";
import type { components } from "@/lib/api-types";
import { getRole } from "@/lib/role";

type S = components["schemas"];
export type Case = S["Case"];
export type CaseListItem = S["CaseListItem"];
export type CaseEvent = S["CaseEvent"];
export type Facility = S["Facility"];
export type MetaResponse = S["MetaResponse"];
export type Recommendation = S["Recommendation"];
export type RouteOption = S["RouteOption"];
export type RouteLeg = S["RouteLeg"];
export type VitalsReading = S["VitalsReading"];
export type News2Result = S["News2Result"];
export type Intake = S["Intake"];
export type SbarSummary = S["SbarSummary"];
export type TrendResponse = S["TrendResponse"];
export type TrackResponse = S["TrackResponse"];
export type TransportAsset = S["TransportAsset"];
export type HospitalCapacity = S["HospitalCapacity"];
export type DemoState = S["DemoState"];
export type DemoStatePatch = S["DemoStatePatch"];
export type GuidanceResponse = S["GuidanceResponse"];
export type ManualVitalsRequest = S["ManualVitalsRequest"];
export type Patient = S["Patient"];
export type ScanJobStatus = S["ScanJobStatus"];
export type BaselineComparison = S["BaselineComparison"];
export type DeteriorationForecast = S["DeteriorationForecast"];
export type TransportMode = S["TransportMode"];
export type Severity = S["Severity"];
export type CaseStatus = S["CaseStatus"];

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const isForm = rest.body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(`${ENGINE_URL}${path}`, {
      ...rest,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      headers: {
        ...(json !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
        "X-Role": getRole(),
        ...headers,
      },
    });
  } catch {
    throw new ApiError("network", "Cannot reach the engine — check your connection", 0);
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

export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const patch = <T>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const fetcher = <T>(path: string) => api<T>(path);
