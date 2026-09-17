import type { ReviewInfo } from "../types";

export default function ConfidenceMeter({ confidence, review }: { confidence: number; review?: ReviewInfo | null }) {
  const value = Math.max(0, Math.min(100, Math.round(confidence)));
  const threshold = Math.max(0, Math.min(100, review?.threshold ?? 95));
  const passed = value >= threshold;
  const reviewId = review?.review_id;
  const label = passed && !review?.required ? "auto-answered" : `pending human review${reviewId ? ` (${reviewId})` : ""}`;
  const reasons = review?.reasons ?? [];
  return (
    <div className={`confidence-meter ${passed ? "pass" : "warn"}`}>
      <div className="confidence-label">
        Confidence {value}/100 <span aria-hidden="true">&middot;</span> {label}
      </div>
      <div
        className="confidence-track"
        role="meter"
        aria-label="Confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value} out of 100, threshold ${threshold}`}
      >
        <div className="confidence-fill" style={{ width: `${value}%` }} />
        <div className="confidence-tick" style={{ left: `${threshold}%` }} title={`Review threshold ${threshold}`} />
      </div>
      {reasons.length > 0 && (
        <ul className="confidence-reasons">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
