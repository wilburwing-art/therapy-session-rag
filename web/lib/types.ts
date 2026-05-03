// TypeScript types mirroring the Pydantic domain models used by the UI.
// Hand-maintained to keep the FE decoupled; regenerate manually when the
// Python schemas change.

export type UUID = string;

export type CurrentUser = {
  id: UUID;
  organization_id: UUID;
  email: string;
  role: string;
  full_name: string | null;
  email_verified_at: string | null;
};

export type CurrentPatient = {
  id: UUID;
  organization_id: UUID;
  email: string;
  full_name: string | null;
};

export type LoginResponse = {
  user_id: UUID;
  organization_id: UUID;
  email: string;
  full_name: string | null;
  expires_at: string;
};

export type LoginChallengeResponse = {
  requires_2fa: true;
  challenge_token: string;
  expires_at: string;
};

export type Enroll2FAResponse = {
  provisioning_uri: string;
  secret: string;
};

export type SessionStatus =
  | "pending"
  | "uploaded"
  | "transcribing"
  | "embedding"
  | "ready"
  | "failed";

export type SessionSummary = {
  id: UUID;
  patient_id: UUID;
  therapist_id: UUID;
  session_date: string;
  status: SessionStatus;
  session_type: "upload" | "video_call";
  recording_duration_seconds: number | null;
  created_at: string;
};

export type HomeworkItem = {
  task: string;
  notes: string | null;
};

// Full tracked homework row from /api/v1/homework/* and
// /api/v1/patients/{id}/homework. Distinct from the recap sub-item
// above (which is JSON inside the recap payload).
export type HomeworkItemRecord = {
  id: UUID;
  session_id: UUID;
  patient_id: UUID;
  task: string;
  notes: string | null;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SessionRecap = {
  id: UUID;
  session_id: UUID;
  brief: string;
  key_topics: string[];
  emotional_tone: string | null;
  homework_assigned: HomeworkItem[];
  follow_ups: string[];
  risk_flags: string[];
  model_name: string;
  generated_at: string;
};

export type RecurringTopic = {
  topic: string;
  session_count: number;
  summary: string | null;
};

export type EmotionalPattern = {
  pattern: string;
  evidence: string | null;
};

export type CopingStrategy = {
  strategy: string;
  notes: string | null;
};

export type PatientThemes = {
  id: UUID;
  patient_id: UUID;
  recurring_topics: RecurringTopic[];
  emotional_patterns: EmotionalPattern[];
  coping_strategies: CopingStrategy[];
  progress_indicators: string[];
  ongoing_concerns: string[];
  source_session_count: number;
  model_name: string;
  generated_at: string;
};

export type ChatSource = {
  session_id: UUID;
  chunk_id: UUID;
  content_preview: string;
  relevance_score: number;
  start_time: number | null;
  speaker: string | null;
};

export type ChatResponse = {
  response: string;
  conversation_id: UUID;
  sources: ChatSource[];
};

export type ConversationMessage = {
  id: UUID;
  role: "user" | "assistant";
  content: string;
  sequence_number: number;
  sources: ChatSource[] | null;
  created_at: string;
};

export type ConversationRead = {
  id: UUID;
  patient_id: UUID;
  organization_id: UUID;
  title: string | null;
  message_count: number;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
};

export type ConversationSummary = {
  id: UUID;
  patient_id: UUID;
  title: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

// Full session detail returned by GET /api/v1/sessions/{id}. Superset of
// SessionSummary with the therapist-only fields and metadata.
export type SessionRead = SessionSummary & {
  consent_id: UUID;
  recording_path: string | null;
  error_message: string | null;
  therapist_notes: string | null;
  session_metadata: Record<string, unknown> | null;
  updated_at: string;
};

export type TranscriptSegment = {
  text: string;
  start_time: number;
  end_time: number;
  speaker: string | null;
  confidence?: number | null;
};

export type RecordingUrlResponse = {
  url: string;
  expires_at: string;
};
