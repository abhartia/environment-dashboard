import "server-only";

import { indicator } from "@/lib/data";
import { entityName } from "@/lib/dash/entities";
import { buildFood, countryStages, dimValues, foodNodeIds } from "@/lib/dash/food-nodes";
import { area, bars, type Built, chapter, credit, dimLabel, headline, latestPeriod, line, matches, periodToX, points, ranking } from "@/lib/dash/kit";
import type { Headline, Series } from "@/lib/dash/types";

/**
 * The food and land chapter: what feeding ourselves does to the climate and the land. Agrifood emissions → where they
 * come from (stage, process, food, animal; food-nodes.ts) → their share of all emissions → by country → food lost before
 * it reaches shops → food wasted in shops, restaurants and homes (tonnes by sector, then per person) → diets compared →
 * land we farm → farmland in hectares, the world's forests (net change, tree cover lost each year, what drives it,
 * where, tropical primary forest) → species at risk.
 */

const AGRIFOOD = "food.faostat.agrifood-emissions-world";
const SHARE = "food.faostat.agrifood-emissions-world.share";
const BY_COUNTRY = "food.faostat.agrifood-emissions-by-country";
const LOSS = "food-loss.faostat.sdg-12-3-1a";
const WASTE = "food-waste.unep-fwi-2024.total";
const WASTE_PER_PERSON = "food-waste.unep-fwi-2024.per-capita";
const DIETS = "food.scarborough-2023.diet-ghg-per-day";
const LAND_SHARE = "land-use.faostat.share-of-land-area";
const LAND_AREA = "land-use.faostat.area";
const THREATENED = "species.iucn-red-list.threatened-share";
const THREATENED_COUNT = "species.iucn-red-list.threatened-count";
const FOREST = "forest.fao-fra-2025.area";
const FOREST_CHANGE = "forest.fao-fra-2025.net-change";
const TREE_LOSS = "forest.gfw.tree-cover-loss";
const DRIVERS = "forest.gfw.tree-cover-loss-by-driver";
const PRIMARY = "forest.gfw.primary-forest-loss";

const TOP = 15;
const FARM = "#8c510a";
const GREY = "#9aa0a6";
const RED = "#b2182b";
const TREE = "#1b7837";
const FIRE = "#c75400";
const RAINFOREST = "#00441b";

const COMMODITIES: { id: string; colour: string }[] = [
  { id: "total", colour: "#0d0d0d" },
  { id: "fruits-and-vegetables", colour: "#1b7837" },
  { id: "roots-tubers-and-oil-bearing-crops", colour: "#946200" },
  { id: "cereals-and-pulses", colour: "#c75400" },
  { id: "meat-and-animal-products", colour: "#b2182b" },
];

/** Land uses, each line opening the view in hectares that splits it further. */
const LAND: { id: string; colour: string; drill: string }[] = [
  { id: "forest-land", colour: TREE, drill: "forest" },
  { id: "permanent-meadows-and-pastures", colour: "#b8860b", drill: "farmland" },
  { id: "cropland", colour: FARM, drill: "farmland" },
];

/**
 * Farmland's two parts as FAO reports them, cropland against zero. FAO's agricultural land is cropland plus permanent
 * meadows and pastures, so it is the headline and never a band stacked with its own parts.
 */
const FARMLAND: { id: string; colour: string }[] = [
  { id: "cropland", colour: FARM },
  { id: "permanent-meadows-and-pastures", colour: "#b8860b" },
];

/**
 * A colour for each of WRI's drivers of tree cover loss: the ones that turn forest into other land for good (permanent
 * agriculture, mining and energy, settlements) in browns and greys, the ones after which trees usually grow back in
 * other hues. A driver without a colour fails the build rather than borrowing another's.
 */
const DRIVER_COLOURS: Record<string, string> = {
  "permanent-agriculture": FARM,
  "hard-commodities": "#5f5f5f",
  "settlements-and-infrastructure": "#7f3b08",
  "shifting-cultivation": "#b8860b",
  logging: "#2166ac",
  wildfire: FIRE,
  "other-natural-disturbances": TREE,
  unknown: GREY,
};
/**
 * UNEP's sectors of food waste, each with a colour. Its value for the sectors together is the headline and never a bar
 * beside its own parts; a sector without a colour fails the build rather than going undrawn.
 */
const WASTE_ALL = "all-three-sectors";
const WASTE_COLOURS: Record<string, string> = { household: FARM, "food-service": "#2166ac", retail: "#7b5ea7" };

/** Drivers whose band opens no view of its own: "unknown" names no cause to follow. */
const NO_DRIVER_VIEW = new Set(["unknown"]);
/** Floating-point slack, in hectares, when checking that the driver bands add up to all loss (as the pipeline does). */
const ADDS_UP_HA = 0.01;

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
    chart: area([{ key: "agrifood", label: "Agrifood systems", colour: FARM, points: points(AGRIFOOD, "WLD"), drill: "stages" }], short, decimals, false),
    drills: [
      { label: "Where food's emissions come from", to: "stages" },
      { label: "Which foods", to: "foods" },
      { label: "Methane from farm animals", to: "animals" },
      { label: "Share of all emissions", to: "share" },
      { label: "Which countries", to: "countries" },
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
    kicker: "Which countries' food systems emit the most",
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

function loss(): Built {
  const { short, decimals } = u(LOSS);
  return {
    id: "loss",
    parent: "root",
    crumb: "Food lost",
    kicker: "Food lost before it reaches the shops",
    headline: headline(LOSS, "WLD", { commodity: "total" }),
    sentence: `of the world's food, by value, was lost after harvest and before the shops in ${headline(LOSS, "WLD", { commodity: "total" }).period}, by FAO. Waste after that is counted separately.`,
    chart: line(
      COMMODITIES.map((c) => ({ key: c.id, label: dimLabel(LOSS, "commodity", c.id), colour: c.colour, points: points(LOSS, "WLD", { commodity: c.id }) })),
      short,
      decimals,
    ),
    drills: [{ label: "Food wasted in shops, restaurants and homes", to: "waste" }],
    credit: credit(LOSS),
    indicators: [LOSS],
  };
}

/**
 * One UNEP food waste indicator for the world: its value for the sectors together (the headline) and each sector's value
 * in the same period, largest first.
 */
function wasteSectors(id: string): { all: Headline; allLabel: string; rows: { id: string; label: string; value: number }[] } {
  const all = headline(id, "WLD", { sector: WASTE_ALL });
  const rows = dimValues(id, "sector")
    .filter((v) => v.id !== WASTE_ALL)
    .map((v) => {
      if (!Object.hasOwn(WASTE_COLOURS, v.id)) throw new Error(`food: no colour for the food waste sector ${v.id}`);
      return { id: v.id, label: v.label, value: headline(id, "WLD", { sector: v.id }, all.period).value };
    })
    .sort((a, b) => b.value - a.value || a.id.localeCompare(b.id));
  if (!rows.length) throw new Error(`food: ${id} has no sector of its own in ${all.period}`);
  return { all, allLabel: dimLabel(id, "sector", WASTE_ALL).toLowerCase(), rows };
}

function wasteBars(id: string, rows: { id: string; label: string; value: number }[], period: string, note: string) {
  const { short, decimals } = u(id);
  return bars(
    rows.map((r) => ({ key: r.id, label: r.label, value: r.value, colour: WASTE_COLOURS[r.id] })),
    short,
    decimals,
    period,
    note,
  );
}

function waste(): Built {
  const { all, allLabel, rows } = wasteSectors(WASTE);
  // The sentence names the largest sector, so a tie for the largest fails the build rather than reading false.
  if (rows[1] && rows[1].value === rows[0].value) throw new Error(`food: ${WASTE} has no single largest sector in ${all.period}`);
  return {
    id: "waste",
    parent: "loss",
    crumb: "Food wasted",
    kicker: "Food wasted in homes, restaurants and shops",
    headline: all,
    sentence: `of food was wasted worldwide in ${all.period} by ${allLabel}, by weight (UNEP). ${rows[0].label} wasted the most.`,
    chart: wasteBars(
      WASTE,
      rows,
      all.period,
      "Estimated by UNEP for each sector worldwide, inedible parts such as bones and peels included. FAO's food lost before the shops is a share of food's value, not a weight, so the two are not added.",
    ),
    drills: [{ label: "Per person", to: "waste-per-person" }],
    credit: credit(WASTE),
    indicators: [WASTE],
  };
}

function wastePerPerson(): Built {
  const { all, allLabel, rows } = wasteSectors(WASTE_PER_PERSON);
  return {
    id: "waste-per-person",
    parent: "waste",
    crumb: "Per person",
    kicker: "Food wasted per person each year",
    headline: all,
    sentence: `of food wasted in ${all.period} by ${allLabel}, as a world average (UNEP): not what any one person throws away.`,
    chart: wasteBars(WASTE_PER_PERSON, rows, all.period, "Estimated by UNEP for each sector as a world average per person, inedible parts included."),
    drills: [],
    credit: credit(WASTE_PER_PERSON),
    indicators: [WASTE_PER_PERSON],
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
      LAND.map((l) => ({ key: l.id, label: dimLabel(LAND_SHARE, "category", l.id), colour: l.colour, points: points(LAND_SHARE, "WLD", { category: l.id }), drill: l.drill })),
      short,
      decimals,
    ),
    drills: [
      { label: "Farmland", to: "farmland" },
      { label: "Forests", to: "forest" },
      { label: "Species at risk", to: "species" },
    ],
    credit: credit(LAND_SHARE),
    indicators: [LAND_SHARE],
  };
}

function farmland(): Built {
  const { short, decimals } = u(LAND_AREA);
  const h = headline(LAND_AREA, "WLD", { category: "agricultural-land" });
  return {
    id: "farmland",
    parent: "land",
    crumb: "Farmland",
    kicker: "Land used for crops and grazing",
    headline: h,
    sentence: `of farmland worldwide in ${h.period}, as FAO counts it: cropland, and permanent meadows and pastures for grazing animals.`,
    chart: area(
      FARMLAND.map((l) => ({ key: l.id, label: dimLabel(LAND_AREA, "category", l.id), colour: l.colour, points: points(LAND_AREA, "WLD", { category: l.id }) })),
      short,
      decimals,
      true,
    ),
    drills: [{ label: "Forests", to: "forest" }],
    credit: credit(LAND_AREA),
    indicators: [LAND_AREA],
  };
}

function forest(): Built {
  const { short, decimals } = u(FOREST);
  const h = headline(FOREST, "WLD");
  return {
    id: "forest",
    parent: "land",
    crumb: "Forests",
    kicker: "The world's forests",
    headline: h,
    sentence: `of forest worldwide in ${h.period}, as countries report it to FAO's forest assessment: land with trees that is not mainly farmed or built on.`,
    chart: area([{ key: "forest", label: indicator(FOREST).title, colour: TREE, points: points(FOREST, "WLD"), drill: "forest-change" }], short, decimals, false),
    drills: [
      { label: "Net change each year", to: "forest-change" },
      { label: "Tree cover lost each year", to: "tree-loss" },
    ],
    credit: credit(FOREST),
    indicators: [FOREST],
  };
}

/** FAO's average net change a year over each interval between its reporting years, oldest first, as bars from zero. */
function forestChange(): Built {
  const ind = indicator(FOREST_CHANGE);
  const h = headline(FOREST_CHANGE, "WLD");
  const ends = h.period.split("/");
  if (ends.length !== 2) throw new Error(`food/forest-change: ${h.period} is not an interval`);
  const rows = ind.observations
    .filter((o) => matches(o, "WLD") && o.value !== null && o.period !== null)
    .sort((a, b) => periodToX(a) - periodToX(b))
    .map((o) => ({ period: o.period as string, value: o.value as number }));
  return {
    id: "forest-change",
    parent: "forest",
    crumb: "Net change",
    kicker: "How much forest area changes each year",
    headline: h,
    sentence: `on average worldwide from ${ends[0]} to ${ends[1]} (FAO): forest gained by planting and natural spread, minus forest lost. Below zero is a net loss, and gains in some places hide losses in others.`,
    chart: bars(
      rows.map((r) => ({ key: r.period, label: r.period.replace("/", "–"), value: r.value, colour: r.value < 0 ? RED : TREE })),
      ind.unit.short,
      ind.display.decimals,
      h.period,
      "Average change a year over each interval between FAO's reporting years; bars in red are net losses.",
    ),
    drills: [{ label: "Tree cover lost each year", to: "tree-loss" }],
    credit: credit(FOREST_CHANGE),
    indicators: [FOREST_CHANGE],
  };
}

function treeLoss(): Built {
  const { short, decimals } = u(TREE_LOSS);
  const h = headline(TREE_LOSS, "WLD", { part: "all" });
  return {
    id: "tree-loss",
    parent: "forest",
    crumb: "Tree cover loss",
    kicker: "Tree cover lost each year",
    headline: h,
    sentence: `of tree cover lost worldwide in ${h.period}, mapped by satellite (University of Maryland, Global Forest Watch). It is not deforestation: it includes fire, plantation harvest and natural disturbance, trees that grow back are not subtracted, and methods changed over the years.`,
    chart: line(
      [
        { key: "all", label: dimLabel(TREE_LOSS, "part", "all"), colour: TREE, points: points(TREE_LOSS, "WLD", { part: "all" }), drill: "tree-loss-drivers" },
        { key: "fire", label: dimLabel(TREE_LOSS, "part", "fire"), colour: FIRE, points: points(TREE_LOSS, "WLD", { part: "fire" }) },
      ],
      short,
      decimals,
    ),
    drills: [
      { label: "What drives it", to: "tree-loss-drivers" },
      { label: "Which countries", to: "tree-loss-countries" },
      { label: "Tropical primary forest", to: "primary-loss" },
    ],
    credit: credit(TREE_LOSS),
    indicators: [TREE_LOSS],
  };
}

function driverColour(driver: string): string {
  const c = DRIVER_COLOURS[driver];
  if (!c) throw new Error(`food: no colour for the tree cover loss driver ${driver}`);
  return c;
}

/** The drivers that open a view of the countries where each took the most tree cover. */
function driverViews(): string[] {
  const year = latestPeriod(DRIVERS);
  return dimValues(DRIVERS, "driver")
    .filter((v) => !NO_DRIVER_VIEW.has(v.id) && ranking(DRIVERS, year, { driver: v.id }).length > 0)
    .map((v) => v.id);
}

/** One place's tree cover loss as a band per driver, in WRI's order; a driver with no loss recorded there is left out. */
function driverSeries(entity: string, withDrills: boolean): Series[] {
  const views = withDrills ? new Set(driverViews()) : new Set<string>();
  return dimValues(DRIVERS, "driver")
    .map((v) => ({
      key: v.id,
      label: v.label,
      colour: driverColour(v.id),
      points: points(DRIVERS, entity, { driver: v.id }),
      ...(views.has(v.id) ? { drill: `driver-${v.id}` } : {}),
    }))
    .filter((s) => s.points.some((p) => p[1] !== null));
}

/**
 * Throws unless one place's driver bands add up to its published all-loss value in every year (and have no year the
 * total lacks), so "the bands add up to all loss" fails the build the moment a refresh makes it untrue.
 */
function checkDriversAddUp(entity: string): void {
  const sums = new Map<number, number>();
  for (const v of dimValues(DRIVERS, "driver"))
    for (const [x, y] of points(DRIVERS, entity, { driver: v.id })) if (y !== null) sums.set(x, (sums.get(x) ?? 0) + y);
  const all = points(TREE_LOSS, entity, { part: "all" });
  for (const [x, total] of all) {
    const sum = sums.get(x);
    const ok = total === null ? sum === undefined : sum !== undefined && Math.abs(sum - total) <= ADDS_UP_HA;
    if (!ok) throw new Error(`food: ${entity}'s tree cover loss by driver does not add up to all loss in ${x}`);
  }
  const years = new Set(all.map((p) => p[0]));
  for (const x of sums.keys()) if (!years.has(x)) throw new Error(`food: ${entity} has tree cover loss by driver in ${x} but no total`);
}

function treeLossDrivers(): Built {
  const { short, decimals } = u(DRIVERS);
  const year = latestPeriod(DRIVERS);
  const ranked = dimValues(DRIVERS, "driver")
    .map((v) => ({ v, value: indicator(DRIVERS).observations.find((o) => matches(o, "WLD", { driver: v.id }) && o.period === year)?.value ?? null }))
    .filter((r): r is { v: { id: string; label: string }; value: number } => r.value !== null)
    .sort((a, b) => b.value - a.value);
  const top = ranked[0];
  if (!top) throw new Error(`food/tree-loss-drivers: no world value in ${year}`);
  checkDriversAddUp("WLD");
  return {
    id: "tree-loss-drivers",
    parent: "tree-loss",
    crumb: "By driver",
    kicker: `Why trees are lost: ${top.v.label.toLowerCase()} is the largest driver`,
    headline: headline(DRIVERS, "WLD", { driver: top.v.id }, year),
    sentence: `of tree cover lost worldwide in ${year} was where ${top.v.label.toLowerCase()} was the main driver (WRI and Google DeepMind). Permanent farms, mines, energy sites and settlements replace trees for good; after fire, logging and shifting cultivation, trees usually grow back. The bands add up to all loss.`,
    chart: area(driverSeries("WLD", true), short, decimals, true),
    drills: [{ label: "Emissions from clearing land for farming", to: "land-clearing" }],
    credit: credit(DRIVERS),
    indicators: [DRIVERS],
  };
}

function driverCountries(driver: string): Built {
  const { short, decimals } = u(DRIVERS);
  const year = latestPeriod(DRIVERS);
  const label = dimLabel(DRIVERS, "driver", driver);
  const ranked = ranking(DRIVERS, year, { driver });
  const top = ranked.slice(0, TOP);
  if (!top.length) throw new Error(`food/driver-${driver}: no country has a ${year} value`);
  return {
    id: `driver-${driver}`,
    parent: "tree-loss-drivers",
    crumb: label,
    kicker: `Where ${label.toLowerCase()} took the most tree cover`,
    headline: headline(DRIVERS, top[0].entity, { driver }, year),
    sentence: `of tree cover lost in ${entityName(top[0].entity)} in ${year} was where ${label.toLowerCase()} was the main driver, the most of any country (WRI and Google DeepMind).`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: driverColour(driver) })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories, by the main driver in each square kilometre.`,
    ),
    drills: [],
    credit: credit(DRIVERS),
    indicators: [DRIVERS],
  };
}

function treeLossCountries(): Built {
  const { short, decimals } = u(TREE_LOSS);
  const year = latestPeriod(TREE_LOSS);
  const ranked = ranking(TREE_LOSS, year, { part: "all" });
  const top = ranked.slice(0, TOP);
  return {
    id: "tree-loss-countries",
    parent: "tree-loss",
    crumb: "By country",
    kicker: "Where the most tree cover was lost",
    headline: headline(TREE_LOSS, top[0].entity, { part: "all" }, year),
    sentence: `of tree cover lost in ${entityName(top[0].entity)} in ${year}, the most of any country, fire included. Select a country to see what drove it.`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: TREE, drill: `tl-${r.entity}` })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories; loss includes fire, logging and plantation harvest.`,
    ),
    drills: [],
    credit: credit(TREE_LOSS),
    indicators: [TREE_LOSS],
  };
}

/** A country's tree cover loss by driver (replaces its single bar). */
function countryTreeLoss(iso: string): Built {
  const { short, decimals } = u(DRIVERS);
  const name = entityName(iso);
  const h = headline(TREE_LOSS, iso, { part: "all" });
  checkDriversAddUp(iso);
  return {
    id: `tl-${iso}`,
    parent: "tree-loss-countries",
    crumb: name,
    kicker: `${name}: tree cover lost, by driver`,
    headline: h,
    sentence: `of tree cover lost in ${name} in ${h.period} (University of Maryland), split by the main driver in each square kilometre (WRI and Google DeepMind). The bands add up to all loss.`,
    chart: area(driverSeries(iso, false), short, decimals, true),
    drills: [],
    credit: credit(TREE_LOSS, DRIVERS),
    indicators: [TREE_LOSS, DRIVERS],
  };
}

function primaryLoss(): Built {
  const { short, decimals } = u(PRIMARY);
  const h = headline(PRIMARY, "WLD");
  return {
    id: "primary-loss",
    parent: "tree-loss",
    crumb: "Primary forest",
    kicker: "Tropical primary forest lost each year",
    headline: h,
    sentence: `of humid tropical primary forest lost in ${h.period}: mature rainforest that had not been cleared and regrown in recent history (University of Maryland). Loss to fire is included.`,
    chart: area([{ key: "primary", label: indicator(PRIMARY).title, colour: RAINFOREST, points: points(PRIMARY, "WLD"), drill: "primary-loss-countries" }], short, decimals, false),
    drills: [{ label: "Which countries", to: "primary-loss-countries" }],
    credit: credit(PRIMARY),
    indicators: [PRIMARY],
  };
}

function primaryLossCountries(): Built {
  const { short, decimals } = u(PRIMARY);
  const year = latestPeriod(PRIMARY);
  const ranked = ranking(PRIMARY, year);
  const top = ranked.slice(0, TOP);
  return {
    id: "primary-loss-countries",
    parent: "primary-loss",
    crumb: "By country",
    kicker: "Where the most tropical primary forest was lost",
    headline: headline(PRIMARY, top[0].entity, {}, year),
    sentence: `of humid tropical primary forest lost in ${entityName(top[0].entity)} in ${year}, the most of any country (University of Maryland).`,
    chart: bars(
      top.map((r) => ({ key: r.entity, label: entityName(r.entity), value: r.value, colour: RAINFOREST })),
      short,
      decimals,
      year,
      `The ${top.length} largest of ${ranked.length} countries and territories with humid tropical primary forest.`,
    ),
    drills: [],
    credit: credit(PRIMARY),
    indicators: [PRIMARY],
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
    drills: [{ label: "How many species", to: "species-count" }],
    credit: credit(THREATENED),
    indicators: [THREATENED],
  };
}

function speciesCount(): Built {
  const ind = indicator(THREATENED_COUNT);
  const all = headline(THREATENED_COUNT, "WLD", { group: "all" });
  const rows = ind.observations
    .filter((o) => o.entity === "WLD" && o.period === all.period && o.value !== null && o.dims.group !== "all")
    .map((o) => ({ group: o.dims.group, value: o.value as number }))
    .sort((a, b) => b.value - a.value || a.group.localeCompare(b.group));
  return {
    id: "species-count",
    parent: "species",
    crumb: "How many",
    kicker: "How many species are threatened",
    headline: all,
    sentence: `on the IUCN Red List were threatened with extinction in ${all.period}: critically endangered, endangered or vulnerable. Only assessed species are counted, and only a small part of insects, plants and fungi has been assessed.`,
    chart: bars(
      rows.map((r) => ({ key: r.group, label: dimLabel(THREATENED_COUNT, "group", r.group), value: r.value, colour: RED })),
      ind.unit.short,
      ind.display.decimals,
      all.period,
      "Threatened species among those assessed in each group; the groups shown do not cover every assessed species.",
    ),
    drills: [],
    credit: credit(THREATENED_COUNT),
    indicators: [THREATENED_COUNT],
  };
}

function countryCodes(): string[] {
  return ranking(BY_COUNTRY, latestPeriod(BY_COUNTRY))
    .slice(0, TOP)
    .map((r) => r.entity);
}

/** The countries on the tree cover loss ranking, each opening its loss by driver. */
function treeLossCodes(): string[] {
  return ranking(TREE_LOSS, latestPeriod(TREE_LOSS), { part: "all" })
    .slice(0, TOP)
    .map((r) => r.entity);
}

/** Nodes with a fixed id, outside food-nodes.ts. */
const FIXED: Record<string, () => Built> = {
  root,
  share,
  countries,
  loss,
  waste,
  "waste-per-person": wastePerPerson,
  diets,
  land,
  farmland,
  forest,
  "forest-change": forestChange,
  "tree-loss": treeLoss,
  "tree-loss-drivers": treeLossDrivers,
  "tree-loss-countries": treeLossCountries,
  "primary-loss": primaryLoss,
  "primary-loss-countries": primaryLossCountries,
  species,
  "species-count": speciesCount,
};

function ids(): string[] {
  return [
    "root",
    ...foodNodeIds(),
    ...Object.keys(FIXED).filter((id) => id !== "root"),
    ...driverViews().map((d) => `driver-${d}`),
    ...treeLossCodes().map((c) => `tl-${c}`),
    ...countryCodes().map((c) => `c-${c}`),
  ];
}

function build(id: string): Built {
  const fixed = Object.hasOwn(FIXED, id) ? FIXED[id] : undefined;
  if (fixed) return fixed();
  const c = id.match(/^c-([A-Z0-9_]+)$/);
  if (c) return countryStages(c[1], BY_COUNTRY);
  const tl = id.match(/^tl-([A-Z0-9_]+)$/);
  if (tl) return countryTreeLoss(tl[1]);
  const driver = id.match(/^driver-(.+)$/);
  if (driver) return driverCountries(driver[1]);
  const node = buildFood(id);
  if (node) return node;
  throw new Error(`unknown food node ${id}`);
}

export const food = chapter(ids, build);
