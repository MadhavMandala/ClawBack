// A one-event calendar file (RFC 5545) that Google Calendar, Apple Calendar and Outlook all open.
// Built in the browser: no calendar sign-in, no new permissions.

// Text values escape backslashes, semicolons, commas and newlines.
const esc = (t: string) => t.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");

// Lines longer than 75 octets continue on the next line after a single space.
function fold(line: string): string {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const out: string[] = [];
  let cur = "";
  let size = 0;
  for (const ch of line) {
    const n = new TextEncoder().encode(ch).length;
    if (size + n > (out.length ? 74 : 75)) {
      out.push(cur);
      cur = "";
      size = 0;
    }
    cur += ch;
    size += n;
  }
  out.push(cur);
  return out.join("\r\n ");
}

const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

/** `date` is "YYYY-MM-DD"; the event is 9:00 to 9:15 in the viewer's own time zone (a floating time). */
export function calendarFile(p: { id: string; title: string; date: string; description: string; url: string | null }): string {
  const day = p.date.slice(0, 10).replace(/-/g, "");
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ClawBack//Cancel reminder//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH", // Outlook opens it as an event to add
    "BEGIN:VEVENT",
    `UID:clawback-${p.id}-${day}@clawback`,
    `DTSTAMP:${stamp(new Date())}`,
    `DTSTART:${day}T090000`,
    "DURATION:PT15M",
    `SUMMARY:${esc(p.title)}`,
    `DESCRIPTION:${esc(p.description)}`,
    ...(p.url ? [`URL:${p.url}`] : []),
    // An alert at the event's start, so Apple Calendar and Outlook actually notify (imports don't add one).
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "TRIGGER:-PT0M",
    `DESCRIPTION:${esc(p.title)}`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.map(fold).join("\r\n") + "\r\n";
}

export function downloadCalendar(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/calendar;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
