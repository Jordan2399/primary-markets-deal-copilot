/** Amounts in the API are whole thousands ("k"). Show them in millions. */
export function fmtK(k: number): string {
  return `${(k / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 })}m`;
}

export function fmtPct(value: number): string {
  return `${value.toLocaleString("en-GB", { maximumFractionDigits: 1 })}%`;
}

export function label(value: string): string {
  return value.replace(/_/g, " ");
}

export function fmtClock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
}
