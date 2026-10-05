"use client";

import { useSyncExternalStore } from "react";

const STALE_DAYS = 9;

/**
 * The status page is built when the weekly check runs. If no check has rebuilt it for longer than a week and a bit,
 * say so: a stale "all fine" would be worse than none. Rendered only in the browser (the build can't know "now").
 */
export function StatusAge({ generatedAt }: { generatedAt: string }) {
  // Whole days are stable between renders (they change once a day), so they are a valid external-store snapshot.
  const days = useSyncExternalStore(
    () => () => {},
    () => Math.floor((Date.now() - Date.parse(generatedAt)) / 86_400_000),
    () => null,
  );
  if (days === null || days <= STALE_DAYS) return null;
  return (
    <p role="status" className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm">
      This status is {days} days old: the weekly check has not run since. Numbers on the site may be older than their
      producers&apos; latest releases.
    </p>
  );
}
