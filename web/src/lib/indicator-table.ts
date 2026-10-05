import type {
  Indicator,
  IndicatorFile,
  Observation,
} from "@/gen/hey-api/types.gen";

/**
 * A published indicator file (data/v1/indicators/<id>.json, an IndicatorFile) stores its observations as columns:
 * `table` holds one array per Observation field, each with one entry per row, and `notes` lists each distinct note
 * once (table.note indexes into it). A column the pipeline leaves out is null in every row: period for an indicator
 * dated in years before 1950, age_bp for calendar time, lower, upper, interval, missing_reason and note when no row
 * has one (pipeline/src/envdash/models.py IndicatorFile).
 *
 * expandIndicator turns the file back into the Indicator the pipeline wrote it from, observations as records in the
 * file's row order, each with every Observation field (keys in the same sorted order as the pipeline's JSON). It does
 * no I/O and has no server-only import, so server pages and client components can both use it. A file whose columns
 * disagree throws rather than rendering partial data.
 */
export function expandIndicator(file: IndicatorFile): Indicator {
  const { table, notes, ...meta } = file;
  const rows = table.entity.length;
  const columns: Record<string, readonly unknown[] | undefined> = {
    age_bp: table.age_bp,
    interval: table.interval,
    lower: table.lower,
    missing_reason: table.missing_reason,
    note: table.note,
    period: table.period,
    status: table.status,
    upper: table.upper,
    value: table.value,
  };
  for (const [dim, values] of Object.entries(table.dims))
    columns[`dims.${dim}`] = values;
  for (const [name, values] of Object.entries(columns)) {
    if (values !== undefined && values.length !== rows) {
      throw new Error(
        `${file.id}: table column ${name} has ${values.length} rows, entity has ${rows}`,
      );
    }
  }

  const dimIds = Object.keys(table.dims);
  const observations: Observation[] = new Array(rows);
  for (let i = 0; i < rows; i++) {
    const dims: Record<string, string> = {};
    for (const d of dimIds) dims[d] = table.dims[d][i];
    observations[i] = {
      age_bp: table.age_bp ? table.age_bp[i] : null,
      dims,
      entity: table.entity[i],
      interval: table.interval ? table.interval[i] : null,
      lower: table.lower ? table.lower[i] : null,
      missing_reason: table.missing_reason ? table.missing_reason[i] : null,
      note: noteAt(file.id, notes, table.note ? table.note[i] : null),
      period: table.period ? table.period[i] : null,
      status: table.status[i],
      upper: table.upper ? table.upper[i] : null,
      value: table.value[i],
    };
  }

  const expanded: Indicator = { ...meta, observations };
  return Object.fromEntries(
    Object.entries(expanded).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  ) as Indicator;
}

function noteAt(
  id: string,
  notes: string[],
  index: number | null,
): string | null {
  if (index === null) return null;
  const text = notes[index];
  if (text === undefined)
    throw new Error(
      `${id}: note index ${index} is outside notes (${notes.length} entries)`,
    );
  return text;
}
