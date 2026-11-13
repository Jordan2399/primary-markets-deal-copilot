/** A plain monogram, not a real bank's logo. */
export default function Brand({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Deal Copilot" className="brand-mark">
      <rect width="32" height="32" rx="7" fill="var(--brand-mark-bg)" />
      <path d="M9 22V10h6.2c3.6 0 5.8 2.2 5.8 6s-2.2 6-5.8 6H9Zm3-2.6h3c2 0 3-1.2 3-3.4s-1-3.4-3-3.4h-3v6.8Z" fill="var(--brand-mark-fg)" />
      <rect x="22.5" y="19.5" width="3" height="2.5" rx="0.6" fill="var(--accent-soft)" />
    </svg>
  );
}
