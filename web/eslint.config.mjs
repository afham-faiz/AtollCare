import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Team convention (§14): components are `export default function (...)` with no name.
      "import/no-anonymous-default-export": "off",
      "react/display-name": "off",
      // Leaflet / Recharts / Presage previews use plain <img> where needed (§14: no next/image).
      "@next/next/no-img-element": "off",
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/lib/api-types.ts"]),
]);

export default eslintConfig;
