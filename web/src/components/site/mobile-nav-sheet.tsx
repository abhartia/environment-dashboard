"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Disclaimers } from "@/components/site/disclaimers";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { FOOTER_NAV, NAV } from "@/lib/site";
import { cn } from "@/lib/utils";

export function MobileNavSheet({
  open,
  onOpenChange,
  returnFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The sheet has no SheetTrigger (the menu button lives in the header), so focus is handed back explicitly. */
  returnFocus: () => void;
}) {
  const pathname = usePathname();
  const item = (href: string, label: string, big: boolean) => {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return (
      <SheetClose asChild key={href}>
        <Link
          href={href}
          aria-current={active ? "page" : undefined}
          className={cn(
            "rounded-md px-2 py-2",
            big ? "text-lg" : "text-sm",
            active ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {label}
        </Link>
      </SheetClose>
    );
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="bg-background"
        aria-describedby={undefined}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          returnFocus();
        }}
      >
        <SheetHeader>
          <SheetTitle className="eyebrow">Menu</SheetTitle>
        </SheetHeader>
        <nav aria-label="Chapters, menu" className="grid gap-1 px-4">
          {NAV.map((n) => item(n.href, n.label, true))}
        </nav>
        <div className="px-4">
          <Separator />
        </div>
        <nav aria-label="About the data, menu" className="grid grid-cols-2 gap-1 px-4">
          {FOOTER_NAV.map((n) => item(n.href, n.label, false))}
        </nav>
        <Disclaimers className="mt-auto px-6 pb-6" />
      </SheetContent>
    </Sheet>
  );
}
