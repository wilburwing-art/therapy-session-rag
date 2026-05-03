"""Integration tests for the therapist auth + signup + magic-link flows.

These exercise the real FastAPI app (via ASGITransport) against the
shared test Postgres. They verify the cookie contract, not just the
service layer.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.main import app
from src.models.db.magic_link import MagicLink
from src.models.db.organization import Organization
from src.models.db.user import User, UserRole


@pytest.mark.asyncio(loop_scope="session")
async def test_register_login_me_logout_round_trip(
    db_session: AsyncSession,
) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            register = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"doc-{uuid.uuid4().hex[:8]}@example.com",
                    "password": "correct horse battery",
                    "full_name": "Dr. Integration",
                    "practice_name": "Integration Test Practice",
                },
            )
            assert register.status_code == 201, register.text
            body = register.json()
            assert body["email"].endswith("@example.com")
            assert "therapyrag_session" in register.cookies

            me = await client.get(
                "/api/v1/auth/me",
                cookies=register.cookies,
            )
            assert me.status_code == 200
            assert me.json()["email"] == body["email"]

            logout = await client.post(
                "/api/v1/auth/logout",
                cookies=register.cookies,
            )
            assert logout.status_code == 204

            me_after = await client.get("/api/v1/auth/me")
            assert me_after.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_login_rejects_wrong_password(db_session: AsyncSession) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"login-test-{uuid.uuid4().hex[:8]}@example.com"
            r = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": "strong-password-1",
                    "full_name": "Dr. Test",
                    "practice_name": "Login Test Practice",
                },
            )
            assert r.status_code == 201

            bad = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong"},
            )
            assert bad.status_code == 401

            good = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "strong-password-1"},
            )
            assert good.status_code == 200
            assert "therapyrag_session" in good.cookies
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_magic_link_issue_and_consume(
    db_session: AsyncSession,
    test_therapist: User,
    test_patient: User,
) -> None:
    # Give the therapist a password so they can log in via the API.
    from src.core.auth import hash_password

    test_therapist.password_hash = hash_password("therapist-pw-1")
    await db_session.flush()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": test_therapist.email, "password": "therapist-pw-1"},
            )
            assert login.status_code == 200, login.text

            # Round-trip the CSRF token the way a browser would: read the
            # non-HttpOnly cookie and echo it in the X-CSRF-Token header.
            csrf_token = login.cookies.get("therapyrag_csrf")
            assert csrf_token, "login should have set a CSRF cookie"

            issue = await client.post(
                "/api/v1/auth/patient/magic-link",
                json={"patient_id": str(test_patient.id)},
                cookies=login.cookies,
                headers={"X-CSRF-Token": csrf_token},
            )
            assert issue.status_code == 201, issue.text
            raw_token = issue.json()["token"]
            assert raw_token

            redeem = await client.post(
                "/api/v1/auth/patient/session",
                json={"token": raw_token},
            )
            assert redeem.status_code == 200
            assert redeem.json()["patient_id"] == str(test_patient.id)
            assert "therapyrag_patient" in redeem.cookies

            # Second redemption of the same token must fail (used_at set).
            redeem_again = await client.post(
                "/api/v1/auth/patient/session",
                json={"token": raw_token},
            )
            assert redeem_again.status_code == 401

            # Token row should be marked used.
            result = await db_session.execute(
                select(MagicLink).where(MagicLink.patient_id == test_patient.id)
            )
            link = result.scalars().first()
            assert link is not None
            assert link.used_at is not None
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_duplicate_email_registration_returns_409(
    db_session: AsyncSession,
) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
            payload = {
                "email": email,
                "password": "password-123",
                "full_name": "Dr. Dup",
                "practice_name": "Dup Practice",
            }
            first = await client.post("/api/v1/auth/register", json=payload)
            assert first.status_code == 201
            second = await client.post("/api/v1/auth/register", json=payload)
            assert second.status_code == 409

            # The failed second registration must not have created a second org.
            result = await db_session.execute(
                select(Organization).where(Organization.name == "Dup Practice")
            )
            orgs = list(result.scalars().all())
            assert len(orgs) == 1
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_api_returns_401_without_any_auth(db_session: AsyncSession) -> None:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/users?role=patient")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_patient_role_cannot_log_in_as_therapist(
    db_session: AsyncSession,
    test_patient: User,
) -> None:
    from src.core.auth import hash_password

    # Give the patient a password even though patients normally don't have one.
    test_patient.password_hash = hash_password("patient-pw-1")
    await db_session.flush()
    assert test_patient.role == UserRole.PATIENT

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": test_patient.email, "password": "patient-pw-1"},
            )
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db_session, None)
