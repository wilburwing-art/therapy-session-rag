export type AssessmentInstrument = "phq9" | "gad7";

export type Assessment = {
  id: string;
  patient_id: string;
  instrument: AssessmentInstrument;
  responses: number[];
  total_score: number;
  severity: string | null;
  notes: string | null;
  administered_at: string;
  created_at: string;
};

export const PHQ9_QUESTIONS = [
  "Little interest or pleasure in doing things",
  "Feeling down, depressed, or hopeless",
  "Trouble falling or staying asleep, or sleeping too much",
  "Feeling tired or having little energy",
  "Poor appetite or overeating",
  "Feeling bad about yourself — or that you are a failure",
  "Trouble concentrating on things",
  "Moving or speaking slowly, or being fidgety or restless",
  "Thoughts that you would be better off dead, or of hurting yourself",
] as const;

export const GAD7_QUESTIONS = [
  "Feeling nervous, anxious, or on edge",
  "Not being able to stop or control worrying",
  "Worrying too much about different things",
  "Trouble relaxing",
  "Being so restless that it's hard to sit still",
  "Becoming easily annoyed or irritable",
  "Feeling afraid as if something awful might happen",
] as const;

export const LIKERT_OPTIONS = [
  { value: 0, label: "Not at all" },
  { value: 1, label: "Several days" },
  { value: 2, label: "More than half the days" },
  { value: 3, label: "Nearly every day" },
] as const;

export function severityColor(severity: string | null): string {
  switch (severity) {
    case "minimal":
      return "bg-emerald-100 text-emerald-900";
    case "mild":
      return "bg-lime-100 text-lime-900";
    case "moderate":
      return "bg-amber-100 text-amber-900";
    case "moderately_severe":
      return "bg-orange-100 text-orange-900";
    case "severe":
      return "bg-red-100 text-red-900";
    default:
      return "bg-slate-100 text-slate-700";
  }
}
