/**
 * Page paths. Indicator ids contain dots (co2.noaa-gml.monthly-mlo); a dot in a URL's last segment can be read as a
 * file extension by static hosts, so data pages nest the id's parts instead: /data/co2/noaa-gml/monthly-mlo.
 * Machine-readable files keep the dotted id: /data/v1/indicators/co2.noaa-gml.monthly-mlo.json.
 */
export function dataPath(id: string, period?: string): string {
  return `/data/${id.split(".").join("/")}${period ? `#${period}` : ""}`;
}

export function idFromSegments(segments: string[]): string {
  return segments.join(".");
}

export function sourcePath(id: string): string {
  return `/sources/${id}`;
}

export function downloadPath(id: string, ext: "json" | "csv"): string {
  return `/data/v1/indicators/${id}.${ext}`;
}
