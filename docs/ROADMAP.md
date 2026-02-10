# Roadmap

## Current State

TherapyRAG is a fully functional RAG-powered backend with:
- Consent management with audit trails
- Audio/video upload and transcription (Deepgram)
- Semantic search via pgvector embeddings
- Patient-facing AI chatbot (Claude)
- Rate limiting and multi-tenant isolation
- CI/CD pipeline with AWS ECS deployment

## Planned Features

### Phase 1: Patient Engagement

**Journaling Tab**
Patient-facing journaling to complement therapy sessions.
- Daily/weekly journal entries with mood tracking
- AI-generated prompts based on session themes
- Private vs therapist-shared entries
- Integration with RAG for personalized insights

**P2P Video Chat** *(in progress)*
Optional peer-to-peer video calls as alternative to file upload.
- WebRTC with STUN/TURN relay
- Client-side recording with MediaRecorder
- Per-organization feature toggle
- Seamless integration with existing transcription pipeline

### Phase 2: Clinical Tools

**AI-Assisted Progress Notes**
Reduce documentation burden for therapists.
- Auto-summarize session transcripts
- Treatment plan suggestions based on session content
- SOAP note generation

**Measurement-Based Care**
Outcome tracking for evidence-based treatment.
- PHQ-9/GAD-7 trend visualization
- Session-over-session progress metrics
- Treatment plan adherence tracking

### Phase 3: Safety & Scale

**Predictive Analytics**
Early intervention through behavioral pattern analysis.
- Session frequency and engagement trends
- Sentiment shift detection
- Proactive outreach triggers

**AI-to-Human Handoff**
Crisis detection with seamless therapist escalation.
- Real-time risk signal detection
- Warm-transfer with conversation context
- 24/7 support mode for urgent situations

## Technical Roadmap

- [ ] WebSocket support for real-time features
- [ ] Streaming chat responses
- [ ] Multi-region deployment
- [ ] Enhanced observability (OpenTelemetry)
