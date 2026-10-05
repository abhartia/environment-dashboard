import "server-only";

import { indicator } from "@/lib/data";
import { type Built, chapter, credit, headline, line, points } from "@/lib/dash/kit";
import type { Series } from "@/lib/dash/types";

/**
 * The seas and ice chapter. Sea level → where the water comes from (each ice source) → the ice itself; and the ocean's
 * other changes: the heat it stores, Arctic sea ice, and acidity.
 */

const GMSL = "gmsl.aviso.monthly";
const SLR_GRL = "sea-level-contribution.imbie-2026.greenland";
const SLR_ATA = "sea-level-contribution.imbie-2026.antarctica";
const SLR_GLACIERS = "sea-level-contribution.wgms-amce.glaciers-cumulative";
const MASS_GRL = "ice-sheet-mass.imbie-2026.greenland";
const MASS_ATA = "ice-sheet-mass.imbie-2026.antarctica";
const GLACIER_MASS = "glacier-mass.wgms-amce.cumulative";
const OHC_700 = "ohc.ncei.yearly-0-700m";
const OHC_2000 = "ohc.ncei.yearly-0-2000m";
const SEA_ICE = "sea-ice-extent.nsidc.arctic-september";
const SEA_ICE_OSISAF = "sea-ice-extent.osisaf.arctic-september";
const PH = "ph.hot-aloha.surface-insitu";
const PCO2 = "pco2.hot-aloha.surface-insitu";

const SEA = "#2166ac";
const GREENLAND = "#4393c3";
const ANTARCTICA = "#053061";
const GLACIERS = "#7b5ea7";
const HEAT = "#b2182b";

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

function root(): Built {
  const { short, decimals } = u(GMSL);
  return {
    id: "root",
    parent: null,
    crumb: "Sea level",
    kicker: "How much the sea has risen",
    headline: headline(GMSL, "WLD"),
    sentence: "higher than the 1993 average, measured from space by satellite altimetry (AVISO), in the latest month.",
    chart: line([{ key: "gmsl", label: "Global mean sea level, from 1993", colour: SEA, points: points(GMSL, "WLD"), drill: "sources" }], short, decimals),
    drills: [
      { label: "Where the water comes from", to: "sources" },
      { label: "Heat stored in the ocean", to: "heat" },
      { label: "Arctic sea ice", to: "sea-ice" },
      { label: "Ocean acidity", to: "acidity" },
    ],
    credit: credit(GMSL),
    indicators: [GMSL],
  };
}

function sources(): Built {
  const { short, decimals } = u(SLR_GRL);
  const s: Series[] = [
    { key: "greenland", label: "Greenland Ice Sheet (from 1971)", colour: GREENLAND, points: points(SLR_GRL, "GRL"), drill: "greenland" },
    { key: "antarctica", label: "Antarctic Ice Sheet (from 1979)", colour: ANTARCTICA, points: points(SLR_ATA, "ATA"), drill: "antarctica" },
    { key: "glaciers", label: "Mountain glaciers (from 1975)", colour: GLACIERS, points: points(SLR_GLACIERS, "WLD"), drill: "glaciers" },
  ];
  return {
    id: "sources",
    parent: "root",
    crumb: "Melting ice",
    kicker: "Melting ice adds to the sea",
    headline: headline(SLR_GRL, "GRL"),
    sentence: "of sea level rise from Greenland's melting ice sheet alone. Warmer water also takes up more room. Select an ice source.",
    chart: line(s, short, decimals),
    drills: [
      { label: "Greenland", to: "greenland" },
      { label: "Antarctica", to: "antarctica" },
      { label: "Glaciers", to: "glaciers" },
    ],
    credit: credit(SLR_GRL, SLR_ATA, SLR_GLACIERS),
    indicators: [SLR_GRL, SLR_ATA, SLR_GLACIERS],
  };
}

function iceSheet(id: "greenland" | "antarctica"): Built {
  const mass = id === "greenland" ? MASS_GRL : MASS_ATA;
  const entity = id === "greenland" ? "GRL" : "ATA";
  const name = id === "greenland" ? "Greenland" : "Antarctica";
  const { short, decimals } = u(mass);
  return {
    id,
    parent: "sources",
    crumb: name,
    kicker: `Ice lost from ${name}`,
    headline: headline(mass, entity),
    sentence: `of ice, the change since the record began (IMBIE). Negative is ice lost to the sea.`,
    chart: line([{ key: id, label: `${name} ice sheet, cumulative change`, colour: id === "greenland" ? GREENLAND : ANTARCTICA, points: points(mass, entity) }], short, decimals),
    drills: [{ label: id === "greenland" ? "Antarctica" : "Greenland", to: id === "greenland" ? "antarctica" : "greenland" }],
    credit: credit(mass),
    indicators: [mass],
  };
}

function glaciers(): Built {
  const { short, decimals } = u(GLACIER_MASS);
  return {
    id: "glaciers",
    parent: "sources",
    crumb: "Glaciers",
    kicker: "Ice lost from the world's glaciers",
    headline: headline(GLACIER_MASS, "WLD"),
    sentence: "of ice since late 1975, from the World Glacier Monitoring Service. Negative is ice lost.",
    chart: line([{ key: "glaciers", label: "Glaciers, cumulative change", colour: GLACIERS, points: points(GLACIER_MASS, "WLD") }], short, decimals),
    drills: [],
    credit: credit(GLACIER_MASS),
    indicators: [GLACIER_MASS],
  };
}

function heat(): Built {
  const { short, decimals } = u(OHC_2000);
  return {
    id: "heat",
    parent: "root",
    crumb: "Ocean heat",
    kicker: "Heat piling up in the ocean",
    headline: headline(OHC_2000, "WLD"),
    sentence: "of heat in the top 2,000 metres of ocean, compared with NCEI's long-term average.",
    chart: line(
      [
        { key: "0-700", label: "Top 700 metres (from 1955)", colour: "#d6604d", points: points(OHC_700, "WLD") },
        { key: "0-2000", label: "Top 2,000 metres (from 2005)", colour: HEAT, points: points(OHC_2000, "WLD") },
      ],
      short,
      decimals,
    ),
    drills: [],
    credit: credit(OHC_2000, OHC_700),
    indicators: [OHC_2000, OHC_700],
  };
}

function seaIce(): Built {
  const { short, decimals } = u(SEA_ICE);
  return {
    id: "sea-ice",
    parent: "root",
    crumb: "Arctic sea ice",
    kicker: "Arctic sea ice at its yearly low",
    headline: headline(SEA_ICE, "NH"),
    sentence: "of Arctic Ocean covered by ice in September, by NSIDC's Sea Ice Index. The second line is Europe's independent OSI SAF record.",
    chart: line(
      [
        { key: "nsidc", label: "NSIDC (US)", colour: SEA, points: points(SEA_ICE, "NH") },
        { key: "osisaf", label: "OSI SAF (Europe)", colour: "#9aa0a6", points: points(SEA_ICE_OSISAF, "NH") },
      ],
      short,
      decimals,
    ),
    drills: [],
    credit: credit(SEA_ICE, SEA_ICE_OSISAF),
    indicators: [SEA_ICE, SEA_ICE_OSISAF],
  };
}

function acidity(): Built {
  const { short, decimals } = u(PH);
  return {
    id: "acidity",
    parent: "root",
    crumb: "Acidity",
    kicker: "The ocean is becoming more acidic",
    headline: headline(PH, "ALOHA"),
    sentence: "at the surface of the North Pacific off Hawaii, at the latest Hawaii Ocean Time-series cruise. Lower pH is more acidic.",
    chart: line([{ key: "ph", label: "Seawater pH, Station ALOHA", colour: SEA, points: points(PH, "ALOHA") }], short, decimals),
    drills: [{ label: "Why: carbon dioxide in the water", to: "pco2" }],
    credit: credit(PH),
    indicators: [PH],
  };
}

function pco2(): Built {
  const { short, decimals } = u(PCO2);
  return {
    id: "pco2",
    parent: "acidity",
    crumb: "Carbon dioxide in the water",
    kicker: "The sea absorbs carbon dioxide from the air",
    headline: headline(PCO2, "ALOHA"),
    sentence: "of carbon dioxide in the surface water at Station ALOHA, at the latest cruise. As it rises, pH falls.",
    chart: line([{ key: "pco2", label: "Carbon dioxide in seawater, Station ALOHA", colour: HEAT, points: points(PCO2, "ALOHA") }], short, decimals),
    drills: [],
    credit: credit(PCO2),
    indicators: [PCO2],
  };
}

function ids(): string[] {
  return ["root", "sources", "greenland", "antarctica", "glaciers", "heat", "sea-ice", "acidity", "pco2"];
}

function build(id: string): Built {
  switch (id) {
    case "root":
      return root();
    case "sources":
      return sources();
    case "greenland":
    case "antarctica":
      return iceSheet(id);
    case "glaciers":
      return glaciers();
    case "heat":
      return heat();
    case "sea-ice":
      return seaIce();
    case "acidity":
      return acidity();
    case "pco2":
      return pco2();
    default:
      throw new Error(`unknown oceans node ${id}`);
  }
}

export const oceans = chapter(ids, build);
