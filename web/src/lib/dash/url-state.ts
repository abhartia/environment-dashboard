"use client";

import { useSyncExternalStore } from "react";

/**
 * Views that live in the URL (?v=<node> in a chapter; ?mode=future&p=…&s=… on the home) change it with pushState or
 * replaceState and then fire NAV_EVENT, so every reader of the URL re-renders; the back button fires popstate.
 */
export const NAV_EVENT = "dash:navigate";

export function subscribe(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  window.addEventListener(NAV_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(NAV_EVENT, onChange);
  };
}

/** The current query string (a stable string, so React re-renders only when it changes); empty on the server. */
export function useSearch(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => "",
  );
}

/**
 * Change the query string in place: `push` adds a history entry (the back button returns to this view), otherwise the
 * current entry is replaced. A key set to null is removed.
 */
export function setSearch(changes: Record<string, string | null>, push: boolean): void {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(changes)) {
    if (v === null) url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  if (url.href === window.location.href) return;
  if (push) window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
  window.dispatchEvent(new Event(NAV_EVENT));
}
