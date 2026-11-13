/** A slice of an answer: plain text, or a citation marker such as S2. */
export type Piece = { type: "text"; text: string } | { type: "cite"; id: string };

/** Split an answer into plain text and citation markers like [S2], so markers can be styled. */
export function splitCitations(text: string): Piece[] {
  const pieces: Piece[] = [];
  // Matches [S1], [S12] ... and captures the number.
  const pattern = /\[S(\d+)\]/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    // Text before this marker (if any) becomes a text piece.
    if (index > last) pieces.push({ type: "text", text: text.slice(last, index) });
    pieces.push({ type: "cite", id: `S${match[1]}` });
    last = index + match[0].length;
  }
  // Whatever follows the last marker.
  if (last < text.length) pieces.push({ type: "text", text: text.slice(last) });
  return pieces;
}

/** "just now", "5 min ago", "yesterday", or a short date: for the thread list. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return ""; // unreadable date: show nothing
  // Step down through units: minutes, hours, days, then a plain date.
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}
