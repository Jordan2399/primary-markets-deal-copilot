import { describe, expect, it } from "vitest";
import { isPaletteShortcut } from "./palette";
import { NAV_LINKS, PERMISSIONS, linksFor } from "./session-utils";

describe("permissions table", () => {
  it("lets the admin do everything", () => {
    for (const p of PERMISSIONS) expect(p.roles).toContain("admin");
  });
  it("lets every role read the basics", () => {
    expect(PERMISSIONS[0].roles).toHaveLength(5);
  });
  it("keeps approval away from the proposing desk", () => {
    const approve = PERMISSIONS.find((p) => p.label.startsWith("Approve"))!;
    const propose = PERMISSIONS.find((p) => p.label.startsWith("Simulate"))!;
    expect(approve.roles).not.toContain("syndicate");
    expect(propose.roles).not.toContain("approver");
  });
});

describe("menu", () => {
  it("shows Reports to everyone and Admin only to admins", () => {
    expect(linksFor("viewer").map((l) => l.href)).toContain("/reports");
    expect(linksFor("syndicate").map((l) => l.href)).not.toContain("/admin");
    expect(linksFor("admin").map((l) => l.href)).toContain("/admin");
    expect(NAV_LINKS.length).toBeGreaterThan(8);
  });
});

describe("search shortcut", () => {
  it("accepts Ctrl+K and Cmd+K only", () => {
    expect(isPaletteShortcut({ key: "k", ctrlKey: true, metaKey: false })).toBe(true);
    expect(isPaletteShortcut({ key: "K", ctrlKey: false, metaKey: true })).toBe(true);
    expect(isPaletteShortcut({ key: "k", ctrlKey: false, metaKey: false })).toBe(false);
    expect(isPaletteShortcut({ key: "j", ctrlKey: true, metaKey: false })).toBe(false);
  });
});
