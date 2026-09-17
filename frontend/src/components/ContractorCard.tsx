import type { Contractor, ResolvedLocation } from "../types";
import { PhoneIcon, StarIcon } from "./Icons";

const MAX_WARRANTIES = 2;

function DiamondGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="tier-diamond">
      <path d="M5 0.5 9.5 5 5 9.5 0.5 5z" fill="currentColor" />
    </svg>
  );
}

function ChipList({ items, max, className }: { items: string[]; max: number; className: string }) {
  if (items.length === 0) return null;
  const shown = items.slice(0, max);
  const extra = items.length - shown.length;
  return (
    <div className={className} title={items.join(", ")}>
      {shown.map((w) => (
        <span key={w} className="tiny-chip">
          {w}
        </span>
      ))}
      {extra > 0 && <span className="tiny-chip">+{extra}</span>}
    </div>
  );
}

export default function ContractorCard({ contractor }: { contractor: Contractor }) {
  const c = contractor;
  const telHref = `tel:${c.phone.replace(/[^\d+]/g, "")}`;
  return (
    <article className="contractor-card">
      <div className="contractor-head">
        <div className="contractor-name">{c.name}</div>
        <span className={`tier-badge tier-${c.certificationTier}`} title={c.yearsCertified != null ? `${c.yearsCertified} years certified` : c.certificationLabel}>
          <DiamondGlyph />
          {c.certificationLabel}
        </span>
      </div>
      <div className="contractor-meta">
        <span className="contractor-rating" aria-label={`Rated ${c.rating.toFixed(1)} from ${c.reviewCount} reviews`}>
          {c.rating.toFixed(1)} <StarIcon size={12} className="star" /> ({c.reviewCount})
        </span>
        <span className="dot-sep" aria-hidden="true">
          &middot;
        </span>
        <span>{c.distanceMiles.toFixed(1)} mi</span>
        <span className="dot-sep" aria-hidden="true">
          &middot;
        </span>
        <span>
          {c.city}, {c.state}
        </span>
      </div>
      <a className="contractor-phone" href={telHref} aria-label={`Call ${c.name} at ${c.phone}`}>
        <PhoneIcon size={13} />
        {c.phone}
      </a>
      <ChipList items={c.warrantiesOffered} max={MAX_WARRANTIES} className="contractor-chips warranties" />
      <ChipList items={c.specialties} max={4} className="contractor-chips specialties" />
      {c.acceptsQuoteRequests && (
        <button type="button" className="chip subtle contractor-quote" aria-label={`Request a quote from ${c.name}`}>
          Request a quote
        </button>
      )}
    </article>
  );
}

export function ContractorList({
  contractors,
  location,
  radiusExpanded,
}: {
  contractors: Contractor[];
  location?: ResolvedLocation | null;
  radiusExpanded?: boolean;
}) {
  const where = location ? ` near ${location.city}, ${location.state} ${location.zip}` : "";
  return (
    <section className="contractor-list" aria-label="Certified contractors">
      <header className="contractor-list-head">
        <strong>
          {contractors.length} certified contractor{contractors.length === 1 ? "" : "s"}
          {where}
        </strong>
        {radiusExpanded && <span className="contractor-list-note">Search radius expanded to find enough results.</span>}
      </header>
      {contractors.length === 0 ? (
        <p className="panel-hint">No certified contractors found in this area.</p>
      ) : (
        <div className="contractor-grid">
          {contractors.map((c) => (
            <ContractorCard key={c.contractorId} contractor={c} />
          ))}
        </div>
      )}
    </section>
  );
}
