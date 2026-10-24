// App identity and client configuration. The product name appears only here and in the README.
export const APP_NAME = "AtollCare";
export const APP_TAGLINE = "The patient's story arrives before the patient does.";

export const ENGINE_URL = process.env.NEXT_PUBLIC_ENGINE_URL || "/api";
// The Presage bridge runs next to the camera (same device as the crew screen).
export const PRESAGE_BRIDGE_URL = process.env.NEXT_PUBLIC_PRESAGE_BRIDGE_URL || "ws://localhost:8787/ws";
export const POLL_MS = 2000;

export const SPONSORS = ["Presage", "ElevenLabs", "Gemini", "Tiger Data", "Vultr"];
