import type { MDXComponents } from "mdx/types";
import Link from "next/link";
import { isValidElement, type ComponentProps, type ReactNode } from "react";

import { Num } from "@/components/data/num";
import { PeriodOf } from "@/components/data/period-of";
import { IndicatorFigure } from "@/components/viz/indicator-figure";
import { WarmingStripes } from "@/components/viz/warming-stripes";
import { slugify } from "@/lib/slugify";
import { cn } from "@/lib/utils";

/** The plain text of a React tree (for heading ids). */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

/**
 * h2/h3 with an id from slugify(text), equal to lib/guides-meta h2Headings, plus a
 * hover anchor. A heading without text has no id to give, so it fails the build.
 * The anchor is for pointer users copying a link: its '#' is CSS-generated and it is
 * hidden from assistive tech and the tab order (the TOC links every section), so the
 * heading's accessible name and crawlable text stay the heading alone.
 */
function anchored(Tag: "h2" | "h3") {
  return function Heading({ children, className, ...rest }: ComponentProps<"h2">) {
    const id = slugify(textOf(children));
    if (!id) throw new Error(`an MDX ${Tag} has no text to derive an id from`);
    return (
      <Tag {...rest} id={id} className={cn("group", className)}>
        {children}
        <a
          href={`#${id}`}
          aria-hidden="true"
          tabIndex={-1}
          className="not-prose ml-2 font-mono text-[0.7em] font-normal text-faint no-underline opacity-0 transition-opacity group-hover:opacity-100 before:content-['#'] hover:text-link"
        />
      </Tag>
    );
  };
}

/**
 * A number, optionally followed by a unit with no further digits ('12.5%', '40.2 Wh', '0.875').
 * Cells that merely start with a number ('10 to < 100') stay text.
 */
const NUMERIC_CELL = /^[−+]?\d[\d.,]*(?:\s?[^\d\s][^\d]*)?$/;

function Td({ children, className, ...rest }: ComponentProps<"td">) {
  const numeric = typeof children === "string" && NUMERIC_CELL.test(children.trim());
  return (
    <td className={cn(numeric && "num text-right whitespace-nowrap", className)} {...rest}>
      {children}
    </td>
  );
}

/** A header cell. An empty corner cell ('| | A | B |') is not a header, so it renders as a plain cell. */
function Th({ children, className, ...rest }: ComponentProps<"th">) {
  if (!textOf(children).trim()) return <td className={cn("bg-muted px-3 py-2 !border-t-0", className)} />;
  return (
    <th className={className} {...rest}>
      {children}
    </th>
  );
}

const components: MDXComponents = {
  a: ({ href = "", children, ...rest }) =>
    href.startsWith("/") ? (
      <Link href={href} {...rest}>
        {children}
      </Link>
    ) : (
      <a href={href} rel="noopener" {...rest}>
        {children}
      </a>
    ),
  h2: anchored("h2"),
  h3: anchored("h3"),
  table: (props) => (
    <div
      tabIndex={0}
      className="not-prose my-6 overflow-x-auto rounded-lg border border-border bg-card outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <table
        className="w-full text-sm [&_td]:border-t [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_th]:bg-muted [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-medium"
        {...props}
      />
    </div>
  ),
  th: Th,
  td: Td,
  Num,
  PeriodOf,
  IndicatorFigure,
  WarmingStripes,
};

export function useMDXComponents(): MDXComponents {
  return components;
}
