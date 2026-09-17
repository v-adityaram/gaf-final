import { useId } from "react";
import type { ProductCard as ProductCardData } from "../types";
import { money } from "../lib/format";

const FALLBACK_HEX = "#8a8d8f";
const MAX_BADGES = 3;

// Blend a hex colour toward black (negative) or white (positive) so the
// shingle rows read as the same colour in different light.
function shade(hex: string, amount: number): string {
  const clean = hex.replace("#", "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
  const n = Number.parseInt(full, 16);
  if (Number.isNaN(n) || full.length !== 6) return hex;
  const mix = (channel: number) => {
    const target = amount < 0 ? 0 : 255;
    const t = Math.abs(amount);
    return Math.round(channel + (target - channel) * t);
  };
  const r = mix((n >> 16) & 255);
  const g = mix((n >> 8) & 255);
  const b = mix(n & 255);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

// Four staggered rows of tabs, like an architectural shingle sample board.
export function ShingleSwatch({ hex, size = 64, imageUrl }: { hex: string | null; size?: number; imageUrl?: string | null }) {
  const uid = useId().replace(/:/g, "");
  const clipId = `shingle-clip-${uid}`;
  const glossId = `shingle-gloss-${uid}`;
  if (imageUrl) {
    return <img className="shingle-swatch" src={imageUrl} alt="" width={size} height={size} loading="lazy" />;
  }
  const base = hex && /^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(hex) ? (hex.startsWith("#") ? hex : `#${hex}`) : FALLBACK_HEX;
  const dark = shade(base, -0.28);
  const light = shade(base, 0.16);
  const rows = 4;
  const rowH = 100 / rows;
  const tabW = 26;
  const tabs: Array<{ x: number; y: number; w: number; fill: string }> = [];
  for (let r = 0; r < rows; r++) {
    const offset = r % 2 === 0 ? 0 : tabW / 2;
    for (let x = -tabW; x < 100 + tabW; x += tabW) {
      const idx = Math.round((x + tabW) / tabW) + r;
      tabs.push({ x: x + offset + 1.5, y: r * rowH + 2, w: tabW - 3, fill: idx % 3 === 0 ? light : idx % 3 === 1 ? base : dark });
    }
  }
  return (
    <svg className="shingle-swatch" width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" style={{ borderRadius: size * 0.16 }}>
      <defs>
        <clipPath id={clipId}>
          <rect x="0" y="0" width="100" height="100" rx="16" />
        </clipPath>
        <linearGradient id={glossId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.28" />
          <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.04" />
          <stop offset="1" stopColor="#000000" stopOpacity="0.16" />
        </linearGradient>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <rect x="0" y="0" width="100" height="100" fill={base} />
        {tabs.map((t, i) => (
          <rect key={i} x={t.x} y={t.y} width={t.w} height={rowH - 3} rx="1.5" fill={t.fill} />
        ))}
        {Array.from({ length: rows }, (_, r) => (
          <rect key={`shadow-${r}`} x="0" y={r * rowH + rowH - 1.5} width="100" height="1.5" fill="#000" opacity="0.28" />
        ))}
        <rect x="0" y="0" width="100" height="100" fill={`url(#${glossId})`} />
      </g>
    </svg>
  );
}

function priceLine(p: ProductCardData) {
  if (p.price_per_square !== null && p.price_per_square !== undefined) {
    return (
      <>
        <strong>{money(p.price_per_square)}</strong> / square
        {p.unit_price !== null && p.unit_price !== undefined && (
          <span className="product-price-alt">
            ({money(p.unit_price)} / {p.price_unit || "bundle"})
          </span>
        )}
      </>
    );
  }
  if (p.unit_price !== null && p.unit_price !== undefined) {
    return (
      <>
        <strong>{money(p.unit_price)}</strong> / {p.price_unit || "bundle"}
      </>
    );
  }
  return <span className="product-price-alt">Price on request</span>;
}

export default function ProductCard({ product, compact = false }: { product: ProductCardData; compact?: boolean }) {
  const colourBits = [product.colour, product.colour_collection].filter(Boolean);
  const badges = product.badges || [];
  const shown = badges.slice(0, MAX_BADGES);
  const extra = badges.length - shown.length;
  return (
    <article className={`product-card${compact ? " compact" : ""}`} title={product.sku}>
      <ShingleSwatch hex={product.swatch_hex} imageUrl={product.image_url} size={compact ? 48 : 64} />
      <div className="product-card-body">
        <div className="product-name">{product.product_name}</div>
        {colourBits.length > 0 && <div className="product-colour">{colourBits.join(" · ")}</div>}
        <div className="product-price">{priceLine(product)}</div>
        {(shown.length > 0 || product.price_tier) && (
          <div className="product-badges">
            {shown.map((b) => (
              <span key={b} className="product-badge">
                {b}
              </span>
            ))}
            {extra > 0 && (
              <span className="product-badge" title={badges.slice(MAX_BADGES).join(", ")}>
                +{extra}
              </span>
            )}
            {product.price_tier && (
              <span className="product-tier" aria-label={`Price tier ${product.price_tier}`}>
                {product.price_tier}
              </span>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

export function ProductCardRow({ products }: { products: ProductCardData[] }) {
  if (products.length === 0) return null;
  return (
    <div className="product-card-row" role="list" aria-label="Matching products">
      {products.map((p) => (
        <div key={p.sku} role="listitem" className="product-card-row-item">
          <ProductCard product={p} compact />
        </div>
      ))}
    </div>
  );
}
