import { cn } from "@/lib/utils";

/** The page column: 16px side gutter on phones, a readable max width on desktop. */
export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>{children}</div>;
}
