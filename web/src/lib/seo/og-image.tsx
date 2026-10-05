import { ImageResponse } from "next/og";

import { indicator } from "@/lib/data";

/** Hex values (satori cannot read CSS variables), matching globals.css. */
const PAPER = "#faf9f6";
const INK = "#16181d";
const MUTED = "#4f5560";
const RDBU = ["#053061", "#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b", "#67001f"];
const STRIPES_ID = "temp.hadcrut5.annual-1850-1900";

/** The warming stripes from the published HadCRUT5 series (same scale as the home page). */
function stripes(): string[] {
  const ind = indicator(STRIPES_ID);
  const values = ind.observations.filter((o) => o.entity === ind.headline_entity && o.value !== null).map((o) => o.value as number);
  const extent = Math.max(...values.map(Math.abs));
  return values.map((v) => RDBU[Math.round(((Math.max(-1, Math.min(1, v / extent)) + 1) / 2) * (RDBU.length - 1))]);
}

function titleSize(title: string): number {
  if (title.length > 90) return 48;
  if (title.length > 60) return 56;
  return 66;
}

/** Shared 1200×630 card: stripes band, eyebrow, title, site name. Text only from the caller; colours from data. */
export function renderOgImage({ eyebrow, title }: { eyebrow: string; title: string }) {
  const colours = stripes();
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: PAPER, color: INK }}>
        <div style={{ display: "flex", height: 120, width: "100%" }}>
          {colours.map((c, i) => (
            <div key={i} style={{ flex: 1, background: c }} />
          ))}
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "48px 64px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ fontSize: 24, letterSpacing: 3, textTransform: "uppercase", color: MUTED }}>{eyebrow}</div>
            <div style={{ fontSize: titleSize(title), fontWeight: 600, lineHeight: 1.08, maxWidth: 1060, letterSpacing: -1 }}>{title}</div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", fontSize: 26, color: MUTED }}>
            <div style={{ display: "flex", fontWeight: 600, color: INK }}>Environment Dashboard</div>
            <div style={{ display: "flex" }}>Every number traced to its source</div>
          </div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
