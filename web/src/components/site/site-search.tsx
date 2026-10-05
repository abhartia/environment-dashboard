"use client";

import dynamic from "next/dynamic";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

// The dialog, cmdk and the index load on first open only.
const SearchDialog = dynamic(() => import("./search-dialog").then((m) => m.SearchDialog), { ssr: false });

export function SiteSearch() {
  const [open, setOpen] = useState(false);
  const [requested, setRequested] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setRequested(true);
        setOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-2 text-muted-foreground"
        aria-haspopup="dialog"
        onClick={() => {
          setRequested(true);
          setOpen(true);
        }}
      >
        <Search aria-hidden="true" />
        <span className="hidden lg:inline">Search</span>
        <kbd className="hidden rounded border border-border px-1 font-sans text-[0.7rem] lg:inline">⌘K</kbd>
        <span className="sr-only lg:hidden">Search</span>
      </Button>
      {requested ? <SearchDialog open={open} onOpenChange={setOpen} /> : null}
    </>
  );
}
