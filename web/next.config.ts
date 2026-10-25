import type { NextConfig } from "next";

// In dev (and when the web container is hit directly) /api/* is proxied to the engine.
// In production Caddy routes /api/* to the engine before it reaches Next.
const ENGINE_INTERNAL_URL = process.env.ENGINE_INTERNAL_URL ?? "http://localhost:8000";
// /presage/* (HTTP and the WebSocket) goes to the Presage bridge, so a phone reaches the app, the API and Presage
// through one HTTPS address (a tunnel to this port): a phone only gets its camera on HTTPS, and an HTTPS page can
// only open wss:// on the same footing.
const PRESAGE_BRIDGE_INTERNAL_URL = process.env.PRESAGE_BRIDGE_INTERNAL_URL ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  output: "standalone",
  // The floating dev badge sits on top of the crew screen's mic button; build/runtime errors still surface.
  devIndicators: false,
  // phones reach the dev server through an HTTPS tunnel; let those hosts load dev assets and hot reload
  allowedDevOrigins: ["*.trycloudflare.com", "*.ngrok-free.app", "*.ngrok.app", "*.loca.lt"],
  turbopack: {
    rules: {
      // Only the global stylesheet needs Tailwind; matching "*.css" would also swallow compiled *.module.scss
      // output and strip its class exports.
      "globals.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${ENGINE_INTERNAL_URL}/api/:path*` },
      { source: "/presage/:path*", destination: `${PRESAGE_BRIDGE_INTERNAL_URL}/presage/:path*` },
    ];
  },
};

export default nextConfig;
