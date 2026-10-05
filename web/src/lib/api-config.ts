import type { CreateClientConfig } from "@/gen/hey-api/client.gen";

/** The data files are served by the site itself (same origin), so the base URL is empty. */
export const createClientConfig: CreateClientConfig = (config) => ({ ...config, baseUrl: "" });
