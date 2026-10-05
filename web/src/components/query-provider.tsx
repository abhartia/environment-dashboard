"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * TanStack Query for the interactive islands only (forms, Plant Check), so the
 * static content pages don't ship the query runtime (pattern from wadecv).
 * One client per mounted provider, created in useState, never at module scope.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { mutations: { retry: 0 } } }));
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
