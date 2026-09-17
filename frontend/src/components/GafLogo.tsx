// Inline GAF logo mark: a brand-red rounded square with bold white "GAF".
// The brand red is the one colour deliberately hardcoded -- it is the
// logo, not UI chrome, so it must not change with the theme.
export default function GafLogo({ size = 30 }: { size?: number }) {
  const radius = size * 0.12;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label="GAF"
      className="gaf-logo"
      style={{ flexShrink: 0, display: "block" }}
    >
      <rect x="0" y="0" width={size} height={size} rx={radius} ry={radius} fill="#c8102e" />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fill="#ffffff"
        fontFamily='"Helvetica Neue", Arial, sans-serif'
        fontWeight={900}
        fontSize={size * 0.42}
        letterSpacing="-0.02em"
        textLength={size * 0.7}
        lengthAdjust="spacingAndGlyphs"
      >
        GAF
      </text>
    </svg>
  );
}

export function GafWordmark() {
  return (
    <span className="gaf-wordmark">
      <GafLogo size={30} />
      <span className="gaf-wordmark-text">Sales Assistant</span>
    </span>
  );
}
