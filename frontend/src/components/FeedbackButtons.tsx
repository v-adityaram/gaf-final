import { useState } from "react";
import { sendFeedback } from "../api";
import { ThumbDownIcon, ThumbUpIcon } from "./Icons";
import type { FeedbackPayload } from "../types";

interface FeedbackButtonsProps {
  context: Omit<FeedbackPayload, "rating" | "comment">;
}

export default function FeedbackButtons({ context }: FeedbackButtonsProps) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [askingWhy, setAskingWhy] = useState(false);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);

  async function submit(chosen: "up" | "down", why?: string) {
    setRating(chosen);
    setAskingWhy(false);
    try {
      await sendFeedback({ ...context, rating: chosen, comment: why || null });
    } catch {
      // best-effort — never interrupt the conversation for telemetry
    }
    setDone(true);
  }

  if (done) {
    return <span className="feedback-thanks">{rating === "up" ? "Marked helpful" : "Flagged for review"}</span>;
  }

  return (
    <span className="feedback">
      <button className="feedback-btn" onClick={() => submit("up")} aria-label="Helpful" title="Helpful">
        <ThumbUpIcon size={14} />
      </button>
      <button
        className={`feedback-btn ${askingWhy ? "active" : ""}`}
        onClick={() => setAskingWhy((v) => !v)}
        aria-label="Not helpful"
        title="Not helpful"
      >
        <ThumbDownIcon size={14} />
      </button>
      {askingWhy && (
        <form
          className="feedback-why"
          onSubmit={(e) => {
            e.preventDefault();
            submit("down", comment.trim());
          }}
        >
          <input
            autoFocus
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What was wrong? (optional)"
            aria-label="What was wrong"
          />
          <button type="submit" className="chip">Send</button>
        </form>
      )}
    </span>
  );
}
