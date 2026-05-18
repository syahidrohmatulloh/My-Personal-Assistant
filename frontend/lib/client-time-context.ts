export type ClientTimeContext = {
  timezone: string;
  local_time: string;
  utc_offset_minutes: number;
  locale: string;
  source: "browser";
  captured_at_utc: string;
};

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function formatLocalTime(date: Date, timeZone: string): string {
  try {
    // sv-SE gives a stable ISO-like local timestamp: YYYY-MM-DD HH:mm:ss.
    return date.toLocaleString("sv-SE", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return date.toLocaleString("sv-SE", { hour12: false });
  }
}

export function buildClientTimeContext(): ClientTimeContext {
  const now = new Date();
  const timezone = getBrowserTimeZone();

  return {
    timezone,
    local_time: formatLocalTime(now, timezone),
    // JavaScript returns minutes behind UTC. Invert it, so Jakarta = +420.
    utc_offset_minutes: -now.getTimezoneOffset(),
    locale: typeof navigator !== "undefined" ? navigator.language : "unknown",
    source: "browser",
    captured_at_utc: now.toISOString(),
  };
}
