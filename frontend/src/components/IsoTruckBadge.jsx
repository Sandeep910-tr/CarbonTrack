/** A compact isometric-style truck glyph, purple->cyan gradient fill,
 * meant to sit as a small badge (not a large illustration) — spec section
 * 35 explicitly warns against 3D visuals big enough to obscure information,
 * so this stays icon-sized and purely decorative. */
export default function IsoTruckBadge({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="isoTruckGrad" x1="4" y1="6" x2="28" y2="26" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#6E6BFF" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <rect x="3" y="12" width="15" height="11" rx="1.5" fill="url(#isoTruckGrad)" opacity="0.9" />
      <path d="M18 12L23 9L28 12V23L18 23V12Z" fill="url(#isoTruckGrad)" opacity="0.65" />
      <path d="M3 12L8 9L23 9L18 12H3Z" fill="url(#isoTruckGrad)" opacity="0.55" />
      <circle cx="9" cy="24" r="2.3" fill="#0A0D16" stroke="#67E8F9" strokeWidth="1.2" />
      <circle cx="22" cy="24" r="2.3" fill="#0A0D16" stroke="#67E8F9" strokeWidth="1.2" />
    </svg>
  );
}
