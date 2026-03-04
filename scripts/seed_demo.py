"""Seed the database with realistic demo data for portfolio demos.

Idempotent — checks if demo org exists before inserting.

Usage:
    uv run python scripts/seed_demo.py
"""

import asyncio
import hashlib
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.security import create_api_key
from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.db.conversation import Conversation, ConversationMessage, MessageRole
from src.models.db.organization import Organization
from src.models.db.session import Session, SessionStatus, SessionType
from src.models.db.session_chunk import SessionChunk
from src.models.db.transcript import Transcript
from src.models.db.user import User, UserRole

DEMO_ORG_NAME = "Mindful Therapy Associates"

# ── Therapy transcript content ──────────────────────────────────────────────

TRANSCRIPTS = [
    {
        "date_offset_days": -21,
        "duration": 2820.0,
        "segments": [
            {
                "speaker": "Speaker 0",
                "text": (
                    "Welcome back. Before we dive in, how has the past week been "
                    "for you overall?"
                ),
                "start": 0.0,
                "end": 5.5,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "It's been a roller coaster, honestly. Work has been really "
                    "stressful with the new project deadline, and I noticed my sleep "
                    "has gotten worse again. I'm waking up around three AM most nights "
                    "with my mind just racing about everything on my to-do list."
                ),
                "start": 6.0,
                "end": 22.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "That sounds exhausting. Sleep disruption and work stress often "
                    "feed into each other. When you wake up at three AM, what kinds "
                    "of thoughts are coming up?"
                ),
                "start": 22.5,
                "end": 31.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "Mostly worry about not being good enough. Like, what if I mess "
                    "up the presentation? What if my team thinks I'm incompetent? "
                    "I know rationally that my work has been fine, but in those dark "
                    "early morning hours, the self-doubt feels so real and overwhelming."
                ),
                "start": 31.5,
                "end": 48.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "You're noticing the gap between what you know rationally and "
                    "what you feel emotionally. That awareness itself is important. "
                    "Let's talk about some strategies for when those nighttime "
                    "thoughts spiral. Have you tried the grounding exercise we "
                    "discussed last time?"
                ),
                "start": 48.5,
                "end": 62.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "I tried it twice. The first time it actually helped — I focused "
                    "on the five senses thing and it kind of brought me back to the "
                    "present moment. The second time I was too agitated and gave up "
                    "after a minute."
                ),
                "start": 62.5,
                "end": 76.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "A minute is still a minute of practice. Progress isn't linear. "
                    "The fact that it worked once shows your brain can learn this "
                    "skill. Let's build on that success and also add a few more "
                    "tools to your toolkit for the harder nights."
                ),
                "start": 76.5,
                "end": 90.0,
            },
        ],
    },
    {
        "date_offset_days": -14,
        "duration": 2940.0,
        "segments": [
            {
                "speaker": "Speaker 0",
                "text": (
                    "Last week we talked about sleep difficulties and work anxiety. "
                    "How have things been since then?"
                ),
                "start": 0.0,
                "end": 6.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "Actually, a little better. I've been doing the grounding "
                    "exercise more consistently. I also started writing down my "
                    "worries before bed — you mentioned a worry journal last month "
                    "and I finally tried it. It's like once the thoughts are on "
                    "paper, my brain gives me permission to set them aside."
                ),
                "start": 6.5,
                "end": 24.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "That's a great insight about externalizing the worry. How has "
                    "your sleep responded?"
                ),
                "start": 24.5,
                "end": 29.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "I slept through the night three times this week. It's not "
                    "perfect, but compared to waking up every single night, it "
                    "feels like a big improvement. I'm less groggy during the day "
                    "and I actually enjoyed working on the project for the first "
                    "time in weeks."
                ),
                "start": 29.5,
                "end": 44.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "Three full nights is significant. I also want to highlight "
                    "something: you said you enjoyed the project. That shift from "
                    "dread to engagement is often one of the first signs that "
                    "anxiety management strategies are working."
                ),
                "start": 44.5,
                "end": 57.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "I hadn't thought of it that way, but you're right. I even "
                    "volunteered to lead a section of the presentation. A month "
                    "ago I would have hidden from that. I think the breathing and "
                    "journaling are helping me feel more in control."
                ),
                "start": 57.5,
                "end": 72.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "Volunteering for the presentation — that takes courage. Let's "
                    "use today's session to prepare you for that. We can do some "
                    "role-play and also talk about managing anxiety in the moment, "
                    "not just before bed."
                ),
                "start": 72.5,
                "end": 85.0,
            },
        ],
    },
    {
        "date_offset_days": -7,
        "duration": 3060.0,
        "segments": [
            {
                "speaker": "Speaker 0",
                "text": (
                    "So, how did the presentation go?"
                ),
                "start": 0.0,
                "end": 2.5,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "It went really well! I was nervous beforehand — my hands were "
                    "shaking and my heart was pounding. But I did the breathing "
                    "technique right before I started speaking, and once I got into "
                    "the material, the anxiety faded into the background. My manager "
                    "said it was one of the best presentations the team has done."
                ),
                "start": 3.0,
                "end": 22.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "That's a meaningful accomplishment. You felt the anxiety, used "
                    "your tools, and performed well despite the nerves. That's "
                    "exactly the pattern we've been working toward."
                ),
                "start": 22.5,
                "end": 32.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "It made me realize that the anxiety doesn't have to stop me. "
                    "Like, I can feel anxious AND still do the thing. Before therapy "
                    "I thought I had to wait until the anxiety went away completely, "
                    "but now I understand it's more about acting alongside it."
                ),
                "start": 32.5,
                "end": 49.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "That's a really important cognitive shift. The goal isn't to "
                    "eliminate anxiety — it's a normal human emotion. The goal is "
                    "to change your relationship with it so it doesn't control your "
                    "choices. How are you feeling about that realization?"
                ),
                "start": 49.5,
                "end": 63.0,
            },
            {
                "speaker": "Speaker 1",
                "text": (
                    "Honestly, kind of empowered. For the first time in a long time, "
                    "I feel like I'm making real progress. The sleep is better, work "
                    "is better, and I'm starting to believe that this stuff actually "
                    "works. I even told my partner about some of the techniques "
                    "and they said they noticed I seem calmer."
                ),
                "start": 63.5,
                "end": 82.0,
            },
            {
                "speaker": "Speaker 0",
                "text": (
                    "When the people around you start noticing changes, it's a strong "
                    "external validation of the internal work you've been doing. "
                    "Let's keep building on this momentum. I'd like to explore "
                    "some longer-term strategies for maintaining these gains."
                ),
                "start": 82.5,
                "end": 96.0,
            },
        ],
    },
]


# ── Embedding generation (matches EmbeddingClient._generate_mock_embeddings) ─

EMBEDDING_DIM = 1536


def _mock_embedding(text: str) -> list[float]:
    """Generate a deterministic mock embedding from text hash."""
    text_hash = hashlib.sha256(text.encode()).digest()
    embedding: list[float] = []
    seed_data = text_hash
    while len(embedding) < EMBEDDING_DIM:
        seed_data = hashlib.sha256(seed_data).digest()
        for byte in seed_data:
            if len(embedding) >= EMBEDDING_DIM:
                break
            embedding.append((byte / 127.5) - 1.0)
    magnitude = sum(x * x for x in embedding) ** 0.5
    return [x / magnitude for x in embedding]


# ── Main seed logic ─────────────────────────────────────────────────────────


async def seed(session: AsyncSession) -> None:
    # Check idempotence
    result = await session.execute(
        select(Organization).where(Organization.name == DEMO_ORG_NAME)
    )
    if result.scalar_one_or_none() is not None:
        print(f"Demo org '{DEMO_ORG_NAME}' already exists — skipping seed.")
        return

    now = datetime.now(UTC)

    # 1. Organization
    org = Organization(id=uuid.uuid4(), name=DEMO_ORG_NAME)
    session.add(org)

    # 2. Users
    therapist = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="dr.martinez@demo.therapyrag.com",
        role=UserRole.THERAPIST,
    )
    patient = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="alex.patient@demo.therapyrag.com",
        role=UserRole.PATIENT,
    )
    session.add_all([therapist, patient])

    # 3. API key
    plain_key, hashed_key = create_api_key()
    from src.models.db.api_key import ApiKey

    api_key = ApiKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        key_hash=hashed_key,
        name="Demo API Key",
        is_active=True,
    )
    session.add(api_key)

    # 4. Consent records
    consent_ids: dict[str, uuid.UUID] = {}
    for ct in [ConsentType.RECORDING, ConsentType.TRANSCRIPTION, ConsentType.AI_ANALYSIS]:
        cid = uuid.uuid4()
        consent_ids[ct] = cid
        session.add(
            Consent(
                id=cid,
                patient_id=patient.id,
                therapist_id=therapist.id,
                consent_type=ct,
                status=ConsentStatus.GRANTED,
                ip_address="127.0.0.1",
                user_agent="seed_demo.py",
            )
        )

    # 5. Sessions, transcripts, chunks
    for t_data in TRANSCRIPTS:
        session_date = now + timedelta(days=t_data["date_offset_days"])
        sess = Session(
            id=uuid.uuid4(),
            patient_id=patient.id,
            therapist_id=therapist.id,
            consent_id=consent_ids[ConsentType.RECORDING],
            session_date=session_date,
            status=SessionStatus.READY,
            session_type=SessionType.UPLOAD,
            recording_duration_seconds=int(t_data["duration"]),
        )
        session.add(sess)

        full_text = " ".join(seg["text"] for seg in t_data["segments"])
        segments_json = [
            {
                "text": seg["text"],
                "start_time": seg["start"],
                "end_time": seg["end"],
                "speaker": seg["speaker"],
                "confidence": 0.97,
            }
            for seg in t_data["segments"]
        ]

        transcript = Transcript(
            id=uuid.uuid4(),
            session_id=sess.id,
            full_text=full_text,
            segments=segments_json,
            word_count=len(full_text.split()),
            duration_seconds=t_data["duration"],
            language="en",
            confidence=0.97,
        )
        session.add(transcript)

        # Create chunks — group every 2-3 segments into a chunk
        chunk_index = 0
        segs = t_data["segments"]
        pos = 0
        while pos < len(segs):
            # Take 2 segments per chunk (last chunk gets remainder)
            chunk_segs = segs[pos : pos + 2]
            chunk_text = " ".join(s["text"] for s in chunk_segs)
            chunk = SessionChunk(
                id=uuid.uuid4(),
                session_id=sess.id,
                transcript_id=transcript.id,
                chunk_index=chunk_index,
                content=chunk_text,
                embedding=_mock_embedding(chunk_text),
                start_time=chunk_segs[0]["start"],
                end_time=chunk_segs[-1]["end"],
                speaker=chunk_segs[0]["speaker"],
                token_count=len(chunk_text) // 4,
            )
            session.add(chunk)
            chunk_index += 1
            pos += 2

    # 6. Conversation with sample messages
    convo = Conversation(
        id=uuid.uuid4(),
        patient_id=patient.id,
        organization_id=org.id,
        title="My therapy progress",
        message_count=2,
    )
    session.add(convo)

    session.add(
        ConversationMessage(
            id=uuid.uuid4(),
            conversation_id=convo.id,
            role=MessageRole.USER,
            content="What techniques have we discussed for managing my anxiety?",
            sequence_number=1,
        )
    )
    session.add(
        ConversationMessage(
            id=uuid.uuid4(),
            conversation_id=convo.id,
            role=MessageRole.ASSISTANT,
            content=(
                "Based on your session records, you and your therapist have "
                "worked on several techniques: grounding exercises using the "
                "five senses, a worry journal before bed to externalize anxious "
                "thoughts, and breathing techniques for managing anxiety in the "
                "moment (like before your presentation). Your therapist noted "
                "that progress isn't linear, and the goal is to change your "
                "relationship with anxiety rather than eliminate it."
            ),
            sequence_number=2,
            sources=[
                {
                    "session_date": (now + timedelta(days=-21)).isoformat(),
                    "content_preview": "grounding exercise... five senses...",
                },
                {
                    "session_date": (now + timedelta(days=-14)).isoformat(),
                    "content_preview": "worry journal... externalizing worry...",
                },
            ],
        )
    )

    await session.commit()

    print("Demo data seeded:")
    print(f"  Organization: {DEMO_ORG_NAME}")
    print(f"  Therapist:    {therapist.email}")
    print(f"  Patient:      {patient.email} (id: {patient.id})")
    print(f"  API Key:      {plain_key}")
    print(f"  Sessions:     {len(TRANSCRIPTS)}")
    print(f"  Org ID:       {org.id}")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
