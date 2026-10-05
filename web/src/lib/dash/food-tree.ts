import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { area, bars, type Built, chapter, credit, dimLabel, headline, latestPeriod, line, points, ranking } from "@/lib/dash/kit";

/**
 * The food and land chapter: what feeding ourselves does to the climate and the land. Agrifood emissions → their
 * share of all emissions → by country → methane from livestock → food lost before it reaches shops → diets compared →
 * land we farm → species at risk.
 */

const AGRIFOOD = "food.faostat.agrifood-emissions-world";
const SHARE = "food.faostat.agrifood-emissions-world.share";
const BY_COUNTRY = "food.faostat.agrifood-emissions-by-country";
const LIVESTOCK = "food.faostat.livestock-ch4-world";
const LOSS = "food-loss.faostat.sdg-12-3-1a";
const DIETS = "food.scarborough-2023.diet-ghg-per-day";
const LAND_SHARE = "land-use.faostat.share-of-land-area";
const THREATENED = "species.iucn-red-list.threatened-share";

const TOP = 15;
const FARM = "#8c510a";
const GREY = "#9aa0a6";

const COMMODITIES: { id: string; colour: string }[] = [
  { id: "total", colour: "#0d0d0d" },
  { id: "fruits-and-vegetables", colour: "#1b7837" },
  { id: "roots-tubers-and-oil-bearing-crops", colour: "#946200" },
  { id: "cereals-and-pulses", colour: "#c75400" },
  { id: "meat-and-animal-products", colour: "#b2182b" },
];

const LAND: { id: string; colour: string }[] = [
  { id: "forest-land", colour: "#1b7837" },
  { id: "permanent-meadows-and-pastures", colour: "#b8860b" },
  { id: "cropland", colour: "#8c510a" },
];

function u(id: string) {
  const ind = indicator(id);
  return { short: ind.unit.short, decimals: ind.display.decimals };
}

function root(): Built {
  const { short, decimals } = u(AGRIFOOD);
  return {
    id: "root",
    parent: null,
    crumb: "Food",
    kicker: "Greenhouse gases from food and farming",
    headline: headline(AGRIFOOD, "WLD"),
    sentence: `in ${latestPeriod(AGRIFOOD)}: on farms, from clearing land for farming, and from processing, transport, shops, kitchens and waste (FAO).`,
    chart: area([{ key: "agrifood", label: "Agrifood systems", colour: FARM, points: points(AGRIFOOD, "WLD"), drill: "share" }], short, decimals, false),
    drills: [
      { label: "Share of all emissions", to: "share" },
      { label: "By country", to: "countries" },
      { label: "Methane from livestock", to: "livestock" },
      { label: "Food lost before the shops", to: "loss" },
      { label: "Diets compared", to: "diets" },
      { label: "The land we farm", to: "land" },
    ],
    credit: credit(AGRIFOOD),
    indicators: [AGRIFOOD],
  };
}

function share(): Built {
  const { short, decimals } = u(SHARE);
  return {
    id: "share",
    parent: "root",
    crumb: "Share of all emissions",
    kicker: "Food's share of all greenhouse gases",
    headline: headline(SHARE, "WLD"),
    sentence: `of the world's greenhouse gas emissions came from food and farming in ${latestPeriod(SHARE)}, by FAO.`,
    chart: line([{ key: "share", label: "Agrifood share of all emissions", colour: FARM, points: points(SHARE, "WLD") }], short, decimals),
    drills: [{ label: "By country", to: "countries" }],
    credit: credit(SHARE),
    indicators: [SHARE],
  };
}

function countries(): Built {
  const { short, decimals } = u(BY_COUNTRY);
  const year = latestPeriod(BY_COUNTRY);
  const ranked = ranking(BY_COUNTRY, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "countries",
    parent: "root",
    crumb: "By country",
    kicker: "Where food emissions come from",
    headline: headline(BY_COUNTRY, top[0].entity, {}, year),
    sentence: `from ${entityName(top[0].entity)}'s food and farming in ${year}, the largest. Select a country.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: FARM, drill: `c-${r.entity}` })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, by FAO's method for every country.`,
    ),
    drills: [],
    credit: credit(BY_COUNTRY),
    indicators: [BY_COUNTRY],
  };
}

function country(iso: string): Built {
  const { short, decimals } = u(BY_COUNTRY);
  const name = entityName(iso);
  return {
    id: `c-${iso}`,
    parent: "countries",
    crumb: name,
    kicker: `${name}: food and farming emissions`,
    headline: headline(BY_COUNTRY, iso),
    sentence: `from ${name}'s food and farming system in ${headline(BY_COUNTRY, iso).period}, by FAO.`,
    chart: area([{ key: iso, label: name, colour: FARM, points: points(BY_COUNTRY, iso) }], short, decimals, false),
    drills: [],
    credit: credit(BY_COUNTRY),
    indicators: [BY_COUNTRY],
  };
}

function livestock(): Built {
  const { short, decimals } = u(LIVESTOCK);
  return {
    id: "livestock",
    parent: "root",
    crumb: "Livestock methane",
    kicker: "Methane from farm animals",
    headline: headline(LIVESTOCK, "WLD"),
    sentence: `a year from livestock worldwide (digestion and manure) in ${latestPeriod(LIVESTOCK)}, by FAO.`,
    chart: area([{ key: "livestock", label: "Methane from livestock", colour: "#c75400", points: points(LIVESTOCK, "WLD") }], short, decimals, false),
    drills: [{ label: "Diets compared", to: "diets" }],
    credit: credit(LIVESTOCK),
    indicators: [LIVESTOCK],
  };
}

function loss(): Built {
  const { short, decimals } = u(LOSS);
  return {
    id: "loss",
    parent: "root",
    crumb: "Food lost",
    kicker: "Food lost before it reaches the shops",
    headline: headline(LOSS, "WLD", { commodity: "total" }),
    sentence: `of the world's food, by value, was lost after harvest and before the shops in ${headline(LOSS, "WLD", { commodity: "total" }).period}, by FAO. Food wasted in shops and homes comes on top.`,
    chart: line(
      COMMODITIES.map((c) => ({ key: c.id, label: dimLabel(LOSS, "commodity", c.id), colour: c.colour, points: points(LOSS, "WLD", { commodity: c.id }) })),
      short,
      decimals,
    ),
    drills: [],
    credit: credit(LOSS),
    indicators: [LOSS],
  };
}

function diets(): Built {
  const ind = indicator(DIETS);
  const rows = ind.observations
    .filter((o) => o.entity === "GBR" && o.value !== null)
    .map((o) => ({ diet: o.dims.diet, value: o.value as number, period: o.period }))
    .sort((a, b) => b.value - a.value);
  const lowest = rows.at(-1)!;
  return {
    id: "diets",
    parent: "root",
    crumb: "Diets compared",
    kicker: "What a day's food costs the climate",
    headline: headline(DIETS, "GBR", { diet: rows[0].diet }, rows[0].period ?? undefined),
    sentence: `a day for ${dimLabel(DIETS, "diet", rows[0].diet).toLowerCase()} in a large UK study (Scarborough et al.), against the least for ${dimLabel(DIETS, "diet", lowest.diet).toLowerCase()}.`,
    chart: bars(
      rows.map((r) => ({ key: r.diet, label: dimLabel(DIETS, "diet", r.diet), value: r.value, colour: r === rows[0] ? "#b2182b" : r === lowest ? "#1b7837" : FARM })),
      ind.unit.short,
      ind.display.decimals,
      rows[0].period ?? "",
      "Per 2,000 kilocalories eaten, by people's own diets in the UK; measured in high-income settings.",
    ),
    drills: [],
    credit: credit(DIETS),
    indicators: [DIETS],
  };
}

function land(): Built {
  const { short, decimals } = u(LAND_SHARE);
  return {
    id: "land",
    parent: "root",
    crumb: "Land",
    kicker: "How the world's land is used",
    headline: headline(LAND_SHARE, "WLD", { category: "agricultural-land" }),
    sentence: `of the world's land area was farmland (crops and pasture) in ${headline(LAND_SHARE, "WLD", { category: "agricultural-land" }).period}, by FAO.`,
    chart: line(
      LAND.map((l) => ({ key: l.id, label: dimLabel(LAND_SHARE, "category", l.id), colour: l.colour, points: points(LAND_SHARE, "WLD", { category: l.id }) })),
      short,
      decimals,
    ),
    drills: [{ label: "Species at risk", to: "species" }],
    credit: credit(LAND_SHARE),
    indicators: [LAND_SHARE],
  };
}

function species(): Built {
  const ind = indicator(THREATENED);
  const rows = ind.observations
    .filter((o) => o.entity === "WLD" && o.value !== null && o.dims.group !== "all")
    .map((o) => ({ group: o.dims.group, value: o.value as number }))
    .sort((a, b) => b.value - a.value);
  const all = headline(THREATENED, "WLD", { group: "all" });
  return {
    id: "species",
    parent: "land",
    crumb: "Species at risk",
    kicker: "Species threatened with extinction",
    headline: all,
    sentence: `of the species assessed for the IUCN Red List are threatened (critically endangered, endangered or vulnerable).`,
    chart: bars(
      rows.map((r) => ({ key: r.group, label: dimLabel(THREATENED, "group", r.group), value: r.value, colour: r.value >= all.value ? "#b2182b" : GREY })),
      ind.unit.short,
      ind.display.decimals,
      all.period,
      "Share of assessed species in each group; groups in red are above the share for all species.",
    ),
    drills: [],
    credit: credit(THREATENED),
    indicators: [THREATENED],
  };
}

function countryCodes(): string[] {
  return ranking(BY_COUNTRY, latestPeriod(BY_COUNTRY))
    .slice(0, TOP)
    .map((r) => r.entity);
}

function ids(): string[] {
  return ["root", "share", "countries", "livestock", "loss", "diets", "land", "species", ...countryCodes().map((c) => `c-${c}`)];
}

function build(id: string): Built {
  if (id === "root") return root();
  if (id === "share") return share();
  if (id === "countries") return countries();
  if (id === "livestock") return livestock();
  if (id === "loss") return loss();
  if (id === "diets") return diets();
  if (id === "land") return land();
  if (id === "species") return species();
  const c = id.match(/^c-([A-Z0-9_]+)$/);
  if (c) return country(c[1]);
  throw new Error(`unknown food node ${id}`);
}

export const food = chapter(ids, build);
