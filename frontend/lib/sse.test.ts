import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses complete events", () => {
    const parser = new SseParser();
    const events = parser.push('event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {"cited":["S1"],"audit_id":null}\n\n');
    expect(events.map((e) => e.event)).toEqual(["token", "done"]);
    expect(events[0].data).toEqual({ text: "Hi" });
  });

  it("keeps a partial event until the rest arrives", () => {
    const parser = new SseParser();
    expect(parser.push('event: token\ndata: {"te')).toEqual([]);
    const events = parser.push('xt":"Hello"}\n\n');
    expect(events).toHaveLength(1);
    expect(events[0].data).toEqual({ text: "Hello" });
  });

  it("handles CRLF line endings and unicode", () => {
    const parser = new SseParser();
    const events = parser.push('event: token\r\ndata: {"text":"€ 750m"}\r\n\r\n');
    expect(events[0].data).toEqual({ text: "€ 750m" });
  });

  it("ignores malformed blocks without throwing", () => {
    const parser = new SseParser();
    expect(parser.push("event: token\ndata: not-json\n\n")).toEqual([]);
    expect(parser.push(": comment\n\n")).toEqual([]);
  });
});
