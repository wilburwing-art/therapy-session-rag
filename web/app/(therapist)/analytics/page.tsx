import { serverFetch } from "@/lib/serverApi";
import { Charts } from "./Charts";
import type {
  ActivePatientsResponse,
  AssessmentTrendResponse,
  ChatActivityPoint,
  SessionsByStatusResponse,
  SessionsByWeekPoint,
} from "./Charts";

export default async function AnalyticsPage() {
  const [
    sessionsByWeek,
    sessionsByStatus,
    activePatients,
    chatActivity,
    phq9Trend,
    gad7Trend,
  ] = await Promise.all([
    serverFetch<SessionsByWeekPoint[]>(
      "/api/v1/analytics/therapist/sessions-by-week",
    ),
    serverFetch<SessionsByStatusResponse>(
      "/api/v1/analytics/therapist/sessions-by-status",
    ),
    serverFetch<ActivePatientsResponse>(
      "/api/v1/analytics/therapist/active-patients",
    ),
    serverFetch<ChatActivityPoint[]>(
      "/api/v1/analytics/therapist/chat-activity",
    ),
    serverFetch<AssessmentTrendResponse>(
      "/api/v1/analytics/therapist/assessment-trend?instrument=phq9",
    ),
    serverFetch<AssessmentTrendResponse>(
      "/api/v1/analytics/therapist/assessment-trend?instrument=gad7",
    ),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold sm:text-3xl">Analytics</h1>
        <p className="mt-1 text-slate-600">
          Practice activity and patient outcomes over time.
        </p>
      </header>
      <Charts
        sessionsByWeek={sessionsByWeek}
        sessionsByStatus={sessionsByStatus}
        activePatients={activePatients}
        chatActivity={chatActivity}
        phq9Trend={phq9Trend}
        gad7Trend={gad7Trend}
      />
    </div>
  );
}
