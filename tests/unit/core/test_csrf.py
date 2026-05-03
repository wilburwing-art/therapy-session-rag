"""Tests for the CSRF middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.csrf import CsrfMiddleware, new_csrf_token


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://u:p@localhost/t",  # type: ignore[arg-type]
        redis_url="redis://localhost:6379",  # type: ignore[arg-type]
        jwt_cookie_secure=False,
    )


def _build_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, settings=settings)

    @app.get("/api/v1/ping")
    def ping() -> dict[str, str]:
        return {"ok": "pong"}

    @app.post("/api/v1/state")
    def state() -> dict[str, str]:
        return {"ok": "mutated"}

    @app.post("/api/v1/auth/login")
    def login_route() -> dict[str, str]:
        return {"ok": "logged-in"}

    @app.post("/api/v1/billing/webhook")
    def webhook() -> dict[str, str]:
        return {"ok": "received"}

    return app


def test_get_requests_are_always_allowed() -> None:
    client = TestClient(_build_app(_settings()))
    res = client.get("/api/v1/ping")
    assert res.status_code == 200


def test_post_without_cookie_is_allowed() -> None:
    client = TestClient(_build_app(_settings()))
    # No session cookie ⇒ API-key or public traffic ⇒ skip CSRF.
    res = client.post("/api/v1/state")
    assert res.status_code == 200


def test_post_with_session_cookie_and_matching_header_allowed() -> None:
    client = TestClient(_build_app(_settings()))
    token = new_csrf_token()
    res = client.post(
        "/api/v1/state",
        cookies={
            "therapyrag_session": "fake-jwt",
            "therapyrag_csrf": token,
        },
        headers={"X-CSRF-Token": token},
    )
    assert res.status_code == 200


def test_post_with_session_cookie_missing_header_rejected() -> None:
    client = TestClient(_build_app(_settings()))
    token = new_csrf_token()
    res = client.post(
        "/api/v1/state",
        cookies={
            "therapyrag_session": "fake-jwt",
            "therapyrag_csrf": token,
        },
    )
    assert res.status_code == 403


def test_post_with_session_cookie_mismatched_header_rejected() -> None:
    client = TestClient(_build_app(_settings()))
    res = client.post(
        "/api/v1/state",
        cookies={
            "therapyrag_session": "fake-jwt",
            "therapyrag_csrf": new_csrf_token(),
        },
        headers={"X-CSRF-Token": new_csrf_token()},
    )
    assert res.status_code == 403


def test_exempt_paths_skip_check_even_with_cookie() -> None:
    client = TestClient(_build_app(_settings()))
    # login / webhook must remain reachable with session cookies but no
    # CSRF token because they either aren't authenticated yet (login)
    # or carry their own signature (webhook).
    login_res = client.post(
        "/api/v1/auth/login",
        cookies={"therapyrag_session": "fake-jwt"},
    )
    assert login_res.status_code == 200

    webhook_res = client.post(
        "/api/v1/billing/webhook",
        cookies={"therapyrag_session": "fake-jwt"},
    )
    assert webhook_res.status_code == 200


def test_patient_session_cookie_is_also_guarded() -> None:
    client = TestClient(_build_app(_settings()))
    res = client.post(
        "/api/v1/state",
        cookies={"therapyrag_patient": "fake-jwt"},
    )
    # Patient session present, no CSRF header ⇒ blocked.
    assert res.status_code == 403
