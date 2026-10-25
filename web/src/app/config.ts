// App identity and client configuration. The product name appears only here and in the README.
export const APP_NAME = "AtollCare";
export const APP_TAGLINE = "The patient's story arrives before the patient does.";

export const ENGINE_URL = process.env.NEXT_PUBLIC_ENGINE_URL || "/api";
// The Presage bridge, reached through this app's own address (/presage/ws, proxied by Next) so a phone on an HTTPS
// tunnel gets wss:// for free. Set NEXT_PUBLIC_PRESAGE_BRIDGE_URL to point somewhere else.
export function presageBridgeUrl(): string {
  if (process.env.NEXT_PUBLIC_PRESAGE_BRIDGE_URL) return process.env.NEXT_PUBLIC_PRESAGE_BRIDGE_URL;
  if (typeof window === "undefined") return "ws://localhost:8787/ws";
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/presage/ws`;
}
export const POLL_MS = 2000;

export const SPONSORS = ["Presage", "ElevenLabs", "Gemini", "Tiger Data", "Vultr"];
