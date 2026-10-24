import type { NextConfig } from "next";

// In dev (and when the web container is hit directly) /api/* is proxied to the engine.
// In production Caddy routes /api/* to the engine before it reaches Next.
const ENGINE_INTERNAL_URL = process.env.ENGINE_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
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
    return [{ source: "/api/:path*", destination: `${ENGINE_INTERNAL_URL}/api/:path*` }];
  },
};

export default nextConfig;
