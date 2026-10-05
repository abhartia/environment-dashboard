"use client";

import dynamic from "next/dynamic";
import { Menu } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

// The Sheet (Radix Dialog) is fetched on the first open only, so it is in no page's first-load JS (gigabiome).
const MobileNavSheet = dynamic(() => import("./mobile-nav-sheet").then((m) => m.MobileNavSheet), { ssr: false });

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const [requested, setRequested] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <>
      <Button
        ref={button}
        variant="ghost"
        size="icon"
        className="xl:hidden"
        aria-label="Open menu"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          setRequested(true);
          setOpen(true);
        }}
      >
        <Menu aria-hidden="true" />
      </Button>
      {requested ? <MobileNavSheet open={open} onOpenChange={setOpen} returnFocus={() => button.current?.focus()} /> : null}
    </>
  );
}
