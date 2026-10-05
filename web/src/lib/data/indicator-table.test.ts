import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import type { IndicatorFile, Observation } from "@/gen/hey-api/types.gen";
import { expandIndicator } from "@/lib/indicator-table";

/**
 * Every public indicator's JSON (columns) must expand to exactly the rows of its CSV (the tidy long format the pipeline
 * writes from the same observations, in the same order): two independent serialisations of one Indicator.
 */
const DATA = path.resolve(__dirname, "../../../../data/v1/indicators");
const FIXED = [
  "indicator_id",
  "entity",
  "period",
  "value",
  "lower",
  "upper",
  "interval",
  "status",
  "note",
  "missing_reason",
  "age_bp",
];

/** RFC 4180 records (quoted fields may hold commas, quotes and newlines). */
function parseCsv(text: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      record.push(field);
      field = "";
    } else if (c === "\n") {
      record.push(field);
      records.push(record);
      record = [];
      field = "";
    } else field += c;
  }
  if (field !== "" || record.length) records.push([...record, field]);
  return records;
}

const text = (s: string): string | null => (s === "" ? null : s);
const num = (s: string): number | null => (s === "" ? null : Number(s));

function rowsOf(csv: string): Observation[] {
  // The '#' header lines come first (export.csv_bytes); the table starts at the first line without one.
  let start = 0;
  while (csv.startsWith("# ", start)) start = csv.indexOf("\n", start) + 1;
  const [header, ...records] = parseCsv(csv.slice(start));
  expect(header.slice(0, FIXED.length)).toEqual(FIXED);
  const dimIds = header.slice(FIXED.length);
  return records.map((r) => ({
    age_bp: num(r[10]),
    dims: Object.fromEntries(dimIds.map((d, j) => [d, r[FIXED.length + j]])),
    entity: r[1],
    interval: text(r[6]) as Observation["interval"],
    lower: num(r[4]),
    missing_reason: text(r[9]),
    note: text(r[8]),
    period: text(r[2]),
    status: r[7] as Observation["status"],
    upper: num(r[5]),
    value: num(r[3]),
  }));
}

const IDS = readdirSync(DATA)
  .filter((f) => f.endsWith(".json"))
  .map((f) => f.slice(0, -".json".length))
  .sort();

describe("expandIndicator", () => {
  it("finds the public exports", () => {
    expect(IDS.length).toBeGreaterThan(50);
  });

  for (const id of IDS) {
    it(`${id}: the columns expand to the CSV's rows`, () => {
      const file = JSON.parse(
        readFileSync(path.join(DATA, `${id}.json`), "utf8"),
      ) as IndicatorFile;
      const ind = expandIndicator(file);
      expect(ind.observations).toEqual(
        rowsOf(readFileSync(path.join(DATA, `${id}.csv`), "utf8")),
      );
      expect("table" in ind || "notes" in ind).toBe(false);
      expect(ind.latest).toEqual(file.latest);
    });
  }

  it("refuses columns of different lengths and a note index outside notes", () => {
    const file = JSON.parse(
      readFileSync(path.join(DATA, "action.ivanova-2020.options.json"), "utf8"),
    ) as IndicatorFile;
    expect(() =>
      expandIndicator({
        ...file,
        table: { ...file.table, value: file.table.value.slice(1) },
      }),
    ).toThrow(/column value has/);
    expect(() => expandIndicator({ ...file, notes: [] })).toThrow(
      /outside notes/,
    );
  });
});
