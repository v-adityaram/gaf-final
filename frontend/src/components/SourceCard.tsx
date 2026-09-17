import { DocIcon } from "./Icons";
import type { Source } from "../types";

interface SourceCardProps {
  source: Source;
}

export default function SourceCard({ source }: SourceCardProps) {
  return (
    <div className="source-card">
      <DocIcon size={16} className="doc-icon" />
      <div>
        <div className="doc-id">{source.document_id}</div>
        <div className="doc-title">{source.title}</div>
        <div className="doc-version">Version {source.version}</div>
      </div>
    </div>
  );
}
