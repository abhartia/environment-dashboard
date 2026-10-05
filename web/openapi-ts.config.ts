import { defineConfig } from "@hey-api/openapi-ts";

// The "API" is the set of static files the pipeline publishes under /data/v1 (pipeline/schema/openapi.json).
// Regenerate after any change to pipeline/src/envdash/models.py: (cd ../pipeline && uv run envdash openapi) && npm run gen:api
export default defineConfig({
  input: "../pipeline/schema/openapi.json",
  output: "src/gen/hey-api",
  plugins: [
    { name: "@hey-api/client-fetch", runtimeConfigPath: "./src/lib/api-config.ts" },
    { name: "@tanstack/react-query", queryOptions: true, queryKeys: true },
  ],
});
