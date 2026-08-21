import { Badge } from "@/components/ui/badge";
import type { Question } from "@/lib/api";

/**
 * The tags that describe a question — kind, measurement, word-cloud-only —
 * used to differ between the case's question list and the report's Select
 * step: different colours, and "lowercase" in one but not the other. One
 * label function and one set of badges now, so a question reads the same
 * wherever it's listed. Each list still places them where its own layout
 * needs them — under the title here, at the row's trailing edge there.
 */

/** "Rating battery · 5" / "Multi-response · 3" / "Comparison · 2" / "Single". */
export function questionKindLabel(q: Question): string {
  switch (q.kind) {
    case "battery":
      return `Rating battery · ${q.variables.length}`;
    case "multi":
      return `Multi-response · ${q.variables.length}`;
    case "comparison":
      return `Comparison · ${q.variables.length}`;
    default:
      return "Single";
  }
}

/** A question's kind — always the same violet badge, whatever the kind. */
export function QuestionKindBadge({ q }: { q: Question }) {
  return (
    <Badge
      variant="outline"
      className="border-violet-200 bg-violet-50 font-normal text-violet-700"
    >
      {questionKindLabel(q)}
    </Badge>
  );
}

/** The measurement badge — adds information only for single/comparison
 *  questions; for multi and battery it would just repeat the kind label, so
 *  it renders nothing there. */
export function QuestionMeasurementBadge({ q }: { q: Question }) {
  const show =
    !!q.measurement && q.measurement !== "multi" && q.measurement !== "rating battery";
  if (!show) return null;
  return (
    <Badge
      variant="outline"
      className="border-teal-200 bg-teal-50 font-normal text-teal-700"
    >
      {q.measurement}
    </Badge>
  );
}

/** A question whose only compatible chart is the word cloud (open-ended free
 *  text) — same teal family as the measurement badge, since it's the same
 *  kind of fact: how this question is read as a chart. */
export function QuestionWordcloudBadge() {
  return (
    <Badge
      variant="outline"
      className="border-teal-200 bg-teal-50 font-normal text-teal-700"
    >
      Word cloud
    </Badge>
  );
}

/** Kind + measurement, wrapped together under a question's title — the case
 *  list's layout. The Select step renders QuestionKindBadge on its own at
 *  the row's trailing edge instead, beside its own state badges. */
export function QuestionTags({ q }: { q: Question }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5">
      <QuestionKindBadge q={q} />
      <QuestionMeasurementBadge q={q} />
    </div>
  );
}
