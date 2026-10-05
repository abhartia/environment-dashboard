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
        {/* Visible where the header has room (lg without the chapter nav, 2xl with it); a screen-reader label elsewhere. */}
        <span className="sr-only lg:not-sr-only xl:sr-only 2xl:not-sr-only">Search</span>
        <kbd className="hidden rounded border border-border px-1 font-sans text-[0.7rem] lg:inline xl:hidden 2xl:inline">⌘K</kbd>
      </Button>
      {requested ? <SearchDialog open={open} onOpenChange={setOpen} /> : null}
    </>
  );
}
