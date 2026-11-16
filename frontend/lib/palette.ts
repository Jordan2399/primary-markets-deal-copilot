/** True for Ctrl+K (Windows/Linux) or Cmd+K (Mac): the shortcut that opens the search palette. */
export function isPaletteShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean }): boolean {
  return (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k";
}
