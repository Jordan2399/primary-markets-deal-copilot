/**
 * The Deal Copilot mark, an original design (not a real bank's logo).
 *
 * Three horizontal bars joined by a stem: an order book. The two outer bars are the orders
 * stacked at each price level and the longer green bar in the middle is the demand peak, the
 * moment a book is covered and the deal can be priced tighter. Colours come from CSS variables
 * so the mark works on the navy top bar, the sign-in panel and in dark mode.
 */
export default function Brand({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Deal Copilot" className="brand-mark">
      <rect width="32" height="32" rx="7.5" fill="var(--brand-mark-bg)" />
      {/* The stem. */}
      <rect x="7.5" y="8" width="3" height="16" rx="1.5" fill="var(--brand-mark-fg)" />
      {/* Orders at the top and bottom price levels, shorter than the demand peak in the middle. */}
      <rect x="7.5" y="8" width="13" height="3.4" rx="1.7" fill="var(--brand-mark-fg)" />
      <rect x="7.5" y="20.6" width="13" height="3.4" rx="1.7" fill="var(--brand-mark-fg)" />
      <rect x="12" y="14.3" width="14" height="3.4" rx="1.7" fill="#0a9a6e" />
    </svg>
  );
}
