import type { ChartSpec, Question } from "@/lib/api";
import { chartTypeLabel, isSpecialSlide } from "@/lib/charts";

export function slideTitle(c: ChartSpec, questionMap: Map<string, Question>): string {
  if (isSpecialSlide(c)) return c.slide_title || chartTypeLabel(c.chart_type);
  return questionMap.get(c.question_ref)?.text ?? c.question_ref;
}
