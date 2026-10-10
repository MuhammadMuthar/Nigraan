// Money arrives from the API as integer paisa. Displayed as Rs with lakh/crore grouping.
const IN = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

export function rs(paisa: number | null | undefined): string {
  if (paisa === null || paisa === undefined) return "—";
  const rupees = paisa / 100;
  return `${rupees < 0 ? "-" : ""}Rs\u00a0${IN.format(Math.abs(rupees))}`; // non-breaking: "Rs" never wraps away from the number
}

/** Short form for chart axes: Rs 14.3L, Rs 1.2Cr */
export function rsShort(paisa: number): string {
  const r = paisa / 100;
  const a = Math.abs(r);
  const sign = r < 0 ? "-" : "";
  if (a >= 1e7) return `${sign}${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${sign}${(a / 1e5).toFixed(1)} L`;
  if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(0)}k`;
  return `${sign}${a.toFixed(0)}`;
}

const TZ = "Asia/Karachi";

export function day(d: string | null | undefined, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!d) return "—";
  // plain dates (YYYY-MM-DD) are calendar dates in Pakistan; don't shift them
  const isPlain = /^\d{4}-\d{2}-\d{2}$/.test(d);
  const dt = isPlain ? new Date(`${d}T12:00:00+05:00`) : new Date(d);
  return dt.toLocaleDateString("en-GB", { timeZone: TZ, day: "numeric", month: "short", ...opts });
}

export function dayFull(d: string | null | undefined): string {
  return day(d, { weekday: "short", year: "numeric" });
}

export function dateTime(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("en-GB", {
    timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true,
  });
}

export function pct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}
