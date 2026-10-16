"use client";

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { SearchItem } from "@/app/search-index.json/route";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { setSearch } from "@/lib/dash/url-state";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Number.POSITIVE_INFINITY } },
});

const GROUPS: { kind: SearchItem["kind"]; heading: string }[] = [
  { kind: "chapter", heading: "Chapters" },
  { kind: "place", heading: "Places: their future" },
  { kind: "data", heading: "Numbers" },
  { kind: "source", heading: "Sources" },
  { kind: "page", heading: "About the data" },
];

export function SearchDialog(props: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <Dialog {...props} />
    </QueryClientProvider>
  );
}

function Dialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const { data, isError } = useQuery({
    queryKey: ["search-index"],
    queryFn: async (): Promise<SearchItem[]> => {
      const res = await fetch("/search-index.json");
      if (!res.ok) throw new Error(`search index: HTTP ${res.status}`);
      return res.json();
    },
  });
  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Search"
      description="Search stories, places, numbers and sources"
    >
      <Command>
        <CommandInput placeholder="Search stories, places, numbers and sources…" value={query} onValueChange={setQuery} />
        <CommandList>
          <CommandEmpty>
            {isError
              ? "The search index could not be loaded."
              : data
                ? "Nothing matches."
                : "Loading…"}
          </CommandEmpty>
          {data
            ? GROUPS.map((g) => {
                // Places are thousands of names: they are listed once the reader has typed something to match.
                if (g.kind === "place" && query.trim().length < 2) return null;
                const items = data.filter((i) => i.kind === g.kind);
                return items.length ? (
                  <CommandGroup key={g.kind} heading={g.heading}>
                    {items.map((i) => (
                      <CommandItem
                        key={i.href}
                        value={`${i.title} ${i.detail}`}
                        onSelect={() => {
                          onOpenChange(false);
                          // On the home page a place opens in place: the map reads its choices from the URL.
                          if (i.kind === "place" && window.location.pathname === "/") {
                            const q = new URLSearchParams(i.href.slice(2));
                            setSearch({ mode: "future", c: q.get("c"), r: q.get("r") }, true);
                          } else router.push(i.href);
                        }}
                      >
                        <span className="grid">
                          <span>{i.title}</span>
                          <span className="text-xs text-muted-foreground">
                            {i.detail}
                          </span>
                        </span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ) : null;
              })
            : null}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
