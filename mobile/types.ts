// Mirror of src/models/domain Pydantic DTOs that the patient-facing
// API returns. Only patient-relevant shapes are included; therapist
// schemas live on the web app.

export type UUID = string;
export type ISODateTime = string;

// --- auth ----------------------------------------------------------

/** POST /auth/patient/session request body. */
export interface MagicLinkRedeemRequest {
  token: string;
}

/** POST /auth/patient/session response body. */
export interface MagicLinkRedeemResponse {
  patient_id: UUID;
  organization_id: UUID;
  expires_at: ISODateTime;
}

/** GET /auth/patient/me response body. */
export interface CurrentPatient {
  id: UUID;
  organization_id: UUID;
  email: string;
  full_name: string | null;
}

// --- chat ----------------------------------------------------------

export interface ChatSource {
  session_id: UUID;
  chunk_id: UUID;
  content_preview: string;
  relevance_score: number;
  start_time: number | null;
  speaker: string | null;
}

/** POST /chat/patient request body. */
export interface ChatRequest {
  message: string;
  conversation_id?: UUID | null;
  top_k?: number;
}

/** POST /chat/patient response body. */
export interface ChatResponse {
  response: string;
  conversation_id: UUID;
  sources: ChatSource[];
}

export interface ConversationSummary {
  id: UUID;
  patient_id: UUID;
  title: string | null;
  message_count: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ConversationMessage {
  id: UUID;
  role: "user" | "assistant";
  content: string;
  sequence_number: number;
  sources: ChatSource[] | null;
  created_at: ISODateTime;
}

export interface ConversationRead {
  id: UUID;
  patient_id: UUID;
  organization_id: UUID;
  title: string | null;
  message_count: number;
  messages: ConversationMessage[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// --- sessions ------------------------------------------------------

export type SessionStatus =
  | "pending"
  | "uploaded"
  | "transcribing"
  | "embedding"
  | "ready"
  | "failed";

export type SessionType = "upload" | "video_call";

/** GET /sessions/patient/{patient_id} entry shape. */
export interface Session {
  id: UUID;
  patient_id: UUID;
  therapist_id: UUID;
  session_date: ISODateTime;
  status: SessionStatus;
  session_type: SessionType;
  recording_duration_seconds: number | null;
  created_at: ISODateTime;
}

// --- local UI state -----------------------------------------------

/** A message as displayed in the chat FlatList. Not a server shape. */
export interface ChatMessageViewModel {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  pending?: boolean;
  error?: boolean;
}

/** Persisted session token + metadata we keep in expo-secure-store. */
export interface StoredSession {
  cookie: string;
  patient_id: UUID;
  organization_id: UUID;
  expires_at: ISODateTime;
  csrf?: string | null;
}
