"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV } from "@/lib/site";
import { cn } from "@/lib/utils";

/** Desktop navigation. The active section gets aria-current and an underline on the header edge. */
export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="hidden h-full items-stretch gap-5 text-sm font-medium xl:flex">
      {NAV.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex items-center whitespace-nowrap transition-colors",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
            {active ? <span aria-hidden="true" className="absolute inset-x-0 -bottom-px h-0.5 bg-foreground" /> : null}
          </Link>
        );
      })}
    </nav>
  );
}
