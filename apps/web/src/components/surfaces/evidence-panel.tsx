// meta: U7 evidence panel, swappable keyed on modality (08 §5 future-modality
// note). text/social_post render the panel text with the evidence span
// highlighted: mono-evidence face, danger-bg tint, 2px danger underline token
// (DESIGN.md evidence-underline). image/video show a day-2 placeholder.
// M4 note: the API serves no material text, so the panel text IS the
// API-served evidence_quote (highlight covers it), and the full checker
// reason renders below it as the analysis line.

import { TriangleAlert } from "lucide-react";
import { PropertyIcon } from "@/components/primitives/property-chip";
import type { FlagView } from "@/lib/data";

const KIND_PREFIX: Record<string, string> = {
  website: "WEB",
  instagram: "IG",
  facebook: "FB",
};

export function EvidencePanel({ view }: { view: FlagView }) {
  const { flag, material, property, meta } = view;

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center gap-2 border-b border-border/60 bg-surface px-4.5 py-2.5">
        <span className="inline-flex h-[22px] items-center gap-1.5 rounded-sm border border-border bg-background px-2 font-mono text-[11px] font-medium text-foreground/70">
          <PropertyIcon kind={property.kind} className="size-3" />
          {KIND_PREFIX[property.kind]}
        </span>
        <span className="text-xs text-muted-foreground">
          {material.ref}
          {meta.postDate ? ` · ${meta.postDate}` : ""}
        </span>
      </div>
      {flag.modality === "text" || flag.modality === "social_post" ? (
        <HighlightedText
          text={material.extracted_text}
          quote={flag.verdicts.evidence_quote}
        />
      ) : (
        <div className="px-6 py-8 text-sm text-muted-foreground">
          Media evidence rendering lands with the multimodal build.
        </div>
      )}
      {flag.verdicts.reason ? (
        <div className="border-t border-border/60 bg-surface/60 px-6 py-3.5">
          <span className="text-xs font-medium text-muted-foreground">
            Checker reasoning
          </span>
          <p className="mt-1 text-xs leading-relaxed text-foreground/70">
            {flag.verdicts.reason}
          </p>
        </div>
      ) : null}
      {meta.missingRequirement ? (
        <div className="mx-6 mb-5 flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-bg px-3.5 py-2.5">
          <TriangleAlert className="mt-0.5 size-3.5 flex-none text-warning" />
          <span className="text-xs text-foreground/70">
            Required nearby, not found:{" "}
            <span className="font-mono">{meta.missingRequirement}</span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

function HighlightedText({ text, quote }: { text: string; quote: string }) {
  const idx = text.indexOf(quote);
  const before = idx >= 0 ? text.slice(0, idx) : text;
  const after = idx >= 0 ? text.slice(idx + quote.length) : "";

  return (
    <div className="flex flex-col gap-2.5 px-6 py-5 text-[14.5px] leading-relaxed text-foreground/80">
      {renderLines(before)}
      {idx >= 0 ? (
        <span>
          <mark className="border-b-2 border-danger bg-danger-bg px-0.5 py-px font-mono text-xs text-foreground">
            {quote}
          </mark>
        </span>
      ) : null}
      {renderLines(after)}
    </div>
  );
}

function renderLines(chunk: string) {
  return chunk
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
    .map((l, i) => <span key={i}>{l}</span>);
}
