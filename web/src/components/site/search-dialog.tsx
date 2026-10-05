"use client";

import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";

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

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Number.POSITIVE_INFINITY } },
});

const GROUPS: { kind: SearchItem["kind"]; heading: string }[] = [
  { kind: "section", heading: "Questions" },
  { kind: "story", heading: "Stories" },
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
      description="Search stories, numbers and sources"
    >
      <Command>
        <CommandInput placeholder="Search stories, numbers and sources…" />
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
                const items = data.filter((i) => i.kind === g.kind);
                return items.length ? (
                  <CommandGroup key={g.kind} heading={g.heading}>
                    {items.map((i) => (
                      <CommandItem
                        key={i.href}
                        value={`${i.title} ${i.detail}`}
                        onSelect={() => {
                          onOpenChange(false);
                          router.push(i.href);
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
