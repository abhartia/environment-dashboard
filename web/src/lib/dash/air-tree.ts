import "server-only";

import { indicator } from "@/lib/data";
import { area, type Built, chapter, credit, headline, line, points } from "@/lib/dash/kit";
import type { Series, SeriesPoint } from "@/lib/dash/types";
import { formatWhen } from "@/lib/format";

/**
 * The air chapter: the greenhouse gases building up in the atmosphere. Carbon dioxide today → over 2,000 years →
 * over 800,000 years → the highest level in the ice before industry; the other long-lived gases; and the extra heat
 * each one traps (radiative forcing).
 */

const MLO = "co2.noaa-gml.monthly-mlo";
const CO2_GLOBAL = "co2.noaa-gml.annual-global";
const LAW_DOME = "co2.law-dome.2k";
const ICE_800K = "co2.bereiter-2015.800k";
const ICE_MAX = "co2.bereiter-2015.800k.max-before-1000bp";
/**
 * The cut-off that defines ICE_MAX (its scope): the highest sample with a gas age above this many years before 1950.
 * A selection rule, not a value: the chart under ICE_MAX shows the same samples, and the node checks that their
 * highest is the published one.
 */
const ICE_MAX_OLDER_THAN_BP = 1000;
const CH4 = "ch4.noaa-gml.annual-global";
const LIVESTOCK_CH4 = "food.faostat.livestock-ch4-world";
const N2O = "n2o.noaa-gml.annual-global";
const FORCING = "forcing.igcc-2025.erf-by-agent";

const CO2_COLOUR = "#b2182b";
const ICE_COLOUR = "#2166ac";
const CH4_COLOUR = "#c75400";
const N2O_COLOUR = "#7b5ea7";

/** Forcing agents shown as lines (IGCC 2025 names); aerosols cool, so their line runs below zero. */
const AGENTS: { id: string; label: string; colour: string }[] = [
  { id: "co2", label: "Carbon dioxide", colour: CO2_COLOUR },
  { id: "ch4", label: "Methane", colour: CH4_COLOUR },
  { id: "n2o", label: "Nitrous oxide", colour: N2O_COLOUR },
  { id: "halogens", label: "Halogenated gases (CFCs and others)", colour: "#946200" },
  { id: "aerosol", label: "Aerosols (cooling)", colour: "#5f5f5f" },
];

function unit(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

function root(): Built {
  const u = unit(MLO);
  const h = headline(MLO, "MLO");
  return {
    id: "root",
    parent: null,
    crumb: "Carbon dioxide",
    kicker: "Carbon dioxide in the air",
    headline: h,
    sentence: `at Mauna Loa, Hawaii, the monthly mean for the latest month measured. The yearly wave is plants breathing in and out with the seasons.`,
    chart: line([{ key: "mlo", label: "Mauna Loa, monthly mean", colour: CO2_COLOUR, points: points(MLO, "MLO") }], u.short, u.decimals),
    drills: [
      { label: "Over 2,000 years", to: "co2-2k" },
      { label: "Over 800,000 years", to: "co2-800k" },
      { label: "Other gases", to: "methane" },
      { label: "The heat they trap", to: "forcing" },
    ],
    credit: credit(MLO),
    indicators: [MLO],
  };
}

function co2Twok(): Built {
  const u = unit(CO2_GLOBAL);
  const s: Series[] = [
    { key: "law-dome", label: "Law Dome ice cores, Antarctica", colour: ICE_COLOUR, points: points(LAW_DOME, "LAWDOME") },
    { key: "global", label: "Measured in the air, global mean", colour: CO2_COLOUR, points: points(CO2_GLOBAL, "WLD") },
  ];
  return {
    id: "co2-2k",
    parent: "root",
    crumb: "2,000 years",
    kicker: "Carbon dioxide over 2,000 years",
    headline: headline(CO2_GLOBAL, "WLD"),
    sentence: "worldwide on average. Air trapped in Antarctic ice gives the level before measurements began.",
    chart: line(s, u.short, u.decimals),
    drills: [{ label: "Further back: 800,000 years", to: "co2-800k" }],
    credit: credit(LAW_DOME, CO2_GLOBAL),
    indicators: [LAW_DOME, CO2_GLOBAL],
  };
}

function co2Ice(): Built {
  const u = unit(ICE_800K);
  // The kicker says the ice record never reached today's level; a refresh that made that false must fail the build.
  const iceMax = Math.max(...points(ICE_800K, "ANT_ICECORES").flatMap((p) => (p[1] === null ? [] : [p[1]])));
  if (headline(CO2_GLOBAL, "WLD").value <= iceMax) throw new Error("air/co2-800k: the kicker's claim no longer holds");
  const s: Series[] = [
    { key: "ice", label: "Antarctic ice cores", colour: ICE_COLOUR, points: points(ICE_800K, "ANT_ICECORES"), drill: "co2-800k-max" },
    { key: "global", label: "Measured in the air, global mean", colour: CO2_COLOUR, points: points(CO2_GLOBAL, "WLD") },
  ];
  return {
    id: "co2-800k",
    parent: "root",
    crumb: "800,000 years",
    kicker: "Higher than at any time in 800,000 years",
    headline: headline(CO2_GLOBAL, "WLD"),
    sentence: `worldwide in ${headline(CO2_GLOBAL, "WLD").period} (the red line), above every level in 800,000 years of air trapped in Antarctic ice (blue).`,
    chart: line(s, u.short, u.decimals),
    drills: [
      { label: "The last 2,000 years", to: "co2-2k" },
      { label: "The highest before industry", to: "co2-800k-max" },
    ],
    credit: credit(ICE_800K, CO2_GLOBAL),
    indicators: [ICE_800K, CO2_GLOBAL],
  };
}

/** The ice-core samples older than ICE_MAX's cut-off (an age before 1950 sits at 1950 minus that age on the axis). */
function iceBeforeCutoff(): SeriesPoint[] {
  return points(ICE_800K, "ANT_ICECORES").filter((p) => p[0] < 1950 - ICE_MAX_OLDER_THAN_BP);
}

function co2IceMax(): Built {
  const u = unit(ICE_MAX);
  const h = headline(ICE_MAX, "ANT_ICECORES");
  // One value, dated by the age of its air (no calendar period): its age is said in words.
  const rows = indicator(ICE_MAX).observations.filter((x) => x.entity === "ANT_ICECORES" && x.value !== null);
  if (rows.length !== 1) throw new Error(`${ICE_MAX}: expected one value, found ${rows.length}`);
  const o = rows[0];
  const ice = iceBeforeCutoff();
  // The kicker says this is the highest level in the ice before industry: the chart's samples must top out at it.
  const shownMax = Math.max(...ice.flatMap((p) => (p[1] === null ? [] : [p[1]])));
  if (shownMax !== h.value) throw new Error(`air/co2-800k-max: the highest sample shown is not ${ICE_MAX}'s value`);
  const before = `${1950 - ICE_MAX_OLDER_THAN_BP} CE`;
  return {
    id: "co2-800k-max",
    parent: "co2-800k",
    crumb: "Before industry",
    kicker: "The highest level before industry",
    headline: h,
    sentence: `in air trapped in Antarctic ice ${formatWhen(o)}: the most in any ice-core sample from before ${before} (Bereiter and others).`,
    chart: line([{ key: "ice", label: `Antarctic ice cores, before ${before}`, colour: ICE_COLOUR, points: ice }], u.short, u.decimals),
    drills: [],
    credit: credit(ICE_MAX, ICE_800K),
    indicators: [ICE_MAX, ICE_800K],
  };
}

function methane(): Built {
  const u = unit(CH4);
  return {
    id: "methane",
    parent: "root",
    crumb: "Methane",
    kicker: "Methane in the air",
    headline: headline(CH4, "WLD"),
    sentence: "worldwide on average, from NOAA's global network of air samples.",
    chart: line([{ key: "ch4", label: "Methane, global mean", colour: CH4_COLOUR, points: points(CH4, "WLD") }], u.short, u.decimals),
    drills: [
      { label: "How much comes from livestock", to: "methane-livestock" },
      { label: "Nitrous oxide", to: "nitrous-oxide" },
    ],
    credit: credit(CH4),
    indicators: [CH4],
  };
}

function methaneLivestock(): Built {
  const u = unit(LIVESTOCK_CH4);
  return {
    id: "methane-livestock",
    parent: "methane",
    crumb: "From livestock",
    kicker: "Methane from farm animals",
    headline: headline(LIVESTOCK_CH4, "WLD"),
    sentence: "a year from livestock worldwide (digestion and manure), as estimated by FAO.",
    chart: area([{ key: "livestock", label: "Methane from livestock", colour: CH4_COLOUR, points: points(LIVESTOCK_CH4, "WLD") }], u.short, u.decimals, false),
    drills: [],
    credit: credit(LIVESTOCK_CH4),
    indicators: [LIVESTOCK_CH4],
  };
}

function nitrousOxide(): Built {
  const u = unit(N2O);
  return {
    id: "nitrous-oxide",
    parent: "root",
    crumb: "Nitrous oxide",
    kicker: "Nitrous oxide in the air",
    headline: headline(N2O, "WLD"),
    sentence: "worldwide on average, from NOAA's global network of air samples.",
    chart: line([{ key: "n2o", label: "Nitrous oxide, global mean", colour: N2O_COLOUR, points: points(N2O, "WLD") }], u.short, u.decimals),
    drills: [{ label: "Methane", to: "methane" }],
    credit: credit(N2O),
    indicators: [N2O],
  };
}

function forcing(): Built {
  const u = unit(FORCING);
  return {
    id: "forcing",
    parent: "root",
    crumb: "Heat trapped",
    kicker: "The extra heat our gases trap",
    headline: headline(FORCING, "WLD", { agent: "anthropogenic" }),
    sentence: "of extra energy reaching the surface, from everything humans have added since 1750, net of the cooling from aerosol pollution.",
    chart: line(
      AGENTS.map((a) => ({ key: a.id, label: a.label, colour: a.colour, points: points(FORCING, "WLD", { agent: a.id }) })),
      u.short,
      u.decimals,
    ),
    drills: [],
    credit: credit(FORCING),
    indicators: [FORCING],
  };
}

function ids(): string[] {
  return ["root", "co2-2k", "co2-800k", "co2-800k-max", "methane", "methane-livestock", "nitrous-oxide", "forcing"];
}

function build(id: string): Built {
  switch (id) {
    case "root":
      return root();
    case "co2-2k":
      return co2Twok();
    case "co2-800k":
      return co2Ice();
    case "co2-800k-max":
      return co2IceMax();
    case "methane":
      return methane();
    case "methane-livestock":
      return methaneLivestock();
    case "nitrous-oxide":
      return nitrousOxide();
    case "forcing":
      return forcing();
    default:
      throw new Error(`unknown air node ${id}`);
  }
}

export const air = chapter(ids, build);
