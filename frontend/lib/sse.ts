import type { CopilotEvent } from "./types";

/**
 * Incremental parser for server-sent events.
 * Feed it text chunks as they arrive; it returns the complete events found so far and keeps
 * any partial event until the rest arrives.
 */
export class SseParser {
  private buffer = "";

  push(chunk: string): CopilotEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: CopilotEvent[] = [];
    let index: number;
    while ((index = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const parsed = parseBlock(block);
      if (parsed) events.push(parsed);
    }
    return events;
  }
}

function parseBlock(block: string): CopilotEvent | null {
  let event = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!event || data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) } as CopilotEvent;
  } catch {
    return null;
  }
}
