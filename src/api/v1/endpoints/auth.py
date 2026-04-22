"""Therapist and patient authentication endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.api.v1.dependencies import CurrentPatient, CurrentTherapist
from src.core.config import Settings, get_settings
from src.core.csrf import (
    clear_csrf_cookie,
    new_csrf_token,
    set_csrf_cookie,
)
from src.core.database import DbSession
from src.models.domain.auth import (
    CurrentPatient as CurrentPatientSchema,
)
from src.models.domain.auth import (
    CurrentUser,
    EmailVerificationConfirm,
    LoginRequest,
    LoginResponse,
    MagicLinkCreateRequest,
    MagicLinkCreateResponse,
    MagicLinkRedeemRequest,
    MagicLinkRedeemResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    RegisterResponse,
)
from src.services.auth_service import AuthService
from src.services.email_service import EmailService, EmailServiceError
from src.services.magic_link_service import MagicLinkService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(session)


def get_magic_link_service(session: DbSession) -> MagicLinkService:
    return MagicLinkService(session)


def get_email_service() -> EmailService:
    return EmailService()


AuthSvc = Annotated[AuthService, Depends(get_auth_service)]
MagicLinkSvc = Annotated[MagicLinkService, Depends(get_magic_link_service)]
EmailSvc = Annotated[EmailService, Depends(get_email_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
PATIENT_COOKIE_NAME = "therapyrag_patient"


def _set_session_cookie(
    response: Response,
    token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_ttl_seconds,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )
    # Pair the session cookie with a CSRF token the JS client reads and
    # echoes back in the X-CSRF-Token header on every mutating request.
    set_csrf_cookie(response, new_csrf_token(), settings)


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.jwt_cookie_name,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )
    clear_csrf_cookie(response, settings)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    auth_service: AuthSvc,
    settings: SettingsDep,
) -> LoginResponse:
    """Authenticate a therapist and set a JWT session cookie."""
    user, token, expires_at = await auth_service.authenticate_therapist(
        email=payload.email,
        password=payload.password,
    )
    _set_session_cookie(response, token, settings)

    return LoginResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        expires_at=expires_at,
    )


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    auth_service: AuthSvc,
    email_service: EmailSvc,
    settings: SettingsDep,
) -> RegisterResponse:
    """Create a new practice (org) plus its founding therapist account.

    The caller is automatically logged in on success. Email is lowercased
    and must be unique across all users. Passwords must be at least 8
    characters. A verification email is dispatched immediately after
    account creation (best-effort — a send failure does not fail the
    signup).
    """
    user, token, expires_at = await auth_service.register_practice(
        email=payload.email,
        password=payload.password,
        practice_name=payload.practice_name,
        full_name=payload.full_name,
    )
    _set_session_cookie(response, token, settings)

    try:
        verification_token = await auth_service.request_email_verification(user.id)
        verification_url = f"{settings.web_app_url}/verify-email?t={verification_token}"
        email_service.send_email_verification(
            to_email=user.email,
            verification_url=verification_url,
            therapist_name=user.full_name,
        )
    except EmailServiceError as exc:
        logger.warning("Verification email send failed for %s: %s", user.id, exc)
    except Exception as exc:
        logger.warning("Could not dispatch verification email for %s: %s", user.id, exc)

    return RegisterResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name or payload.full_name,
        practice_name=payload.practice_name,
        expires_at=expires_at,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    settings: SettingsDep,
) -> Response:
    """Clear the session cookie. Idempotent.

    The cookie-deletion Set-Cookie headers must ride on the same
    `response` object FastAPI returns to the client; returning a fresh
    `Response(status_code=204)` would discard them.
    """
    _clear_session_cookie(response, settings)
    response.status_code = 204
    return response


@router.get("/me", response_model=CurrentUser)
async def me(current_user: CurrentTherapist) -> CurrentUser:
    """Return the authenticated therapist's identity."""
    return CurrentUser.model_validate(current_user)


@router.post(
    "/patient/magic-link",
    response_model=MagicLinkCreateResponse,
    status_code=201,
)
async def create_patient_magic_link(
    payload: MagicLinkCreateRequest,
    magic_link_service: MagicLinkSvc,
    auth_service: AuthSvc,
    email_service: EmailSvc,
    settings: SettingsDep,
    therapist: CurrentTherapist,
) -> MagicLinkCreateResponse:
    """Issue a one-time magic link for a patient.

    The caller must be the patient's therapist (same organization).
    The link is emailed directly to the patient; the raw token is
    also returned in the response so the therapist can copy/share
    it manually if needed.
    """
    raw_token, expires_at = await magic_link_service.issue_link(
        patient_id=payload.patient_id,
        created_by_user_id=therapist.id,
        organization_id=therapist.organization_id,
    )

    # Best-effort email: failures are logged but don't fail the request,
    # since the therapist can still copy the token from the response.
    patient = await auth_service.get_user_by_id(payload.patient_id)
    magic_link_url = f"{settings.web_app_url}/chat?t={raw_token}"
    try:
        email_service.send_magic_link(
            to_email=patient.email,
            magic_link_url=magic_link_url,
            therapist_name=therapist.full_name or therapist.email,
            patient_name=patient.full_name,
        )
    except EmailServiceError as exc:
        logger.warning(
            "Failed to email magic link to %s: %s", patient.email, exc
        )

    return MagicLinkCreateResponse(token=raw_token, expires_at=expires_at)


@router.post("/patient/session", response_model=MagicLinkRedeemResponse)
async def redeem_patient_magic_link(
    payload: MagicLinkRedeemRequest,
    response: Response,
    magic_link_service: MagicLinkSvc,
    settings: SettingsDep,
) -> MagicLinkRedeemResponse:
    """Redeem a magic link and start a patient session.

    Returns 401 for invalid, expired, or already-consumed links. On
    success sets the patient session cookie.
    """
    patient, token, expires_at = await magic_link_service.consume_link(payload.token)
    response.set_cookie(
        key=PATIENT_COOKIE_NAME,
        value=token,
        max_age=settings.magic_link_ttl_seconds,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )
    set_csrf_cookie(
        response,
        new_csrf_token(),
        settings,
        max_age=settings.magic_link_ttl_seconds,
    )
    return MagicLinkRedeemResponse(
        patient_id=patient.id,
        organization_id=patient.organization_id,
        expires_at=expires_at,
    )


@router.post("/patient/logout", status_code=204)
async def patient_logout(response: Response, settings: SettingsDep) -> Response:
    response.delete_cookie(
        key=PATIENT_COOKIE_NAME,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )
    clear_csrf_cookie(response, settings)
    response.status_code = 204
    return response


@router.get("/patient/me", response_model=CurrentPatientSchema)
async def patient_me(patient: CurrentPatient) -> CurrentPatientSchema:
    """Return the authenticated patient's identity."""
    return CurrentPatientSchema.model_validate(patient)


@router.post("/password-reset-request", status_code=202)
async def password_reset_request(
    payload: PasswordResetRequest,
    auth_service: AuthSvc,
    email_service: EmailSvc,
    settings: SettingsDep,
) -> dict[str, bool]:
    """Send a password-reset email if the address matches an account.

    Always returns 202 with `sent: true` regardless of whether the
    user exists, to avoid leaking which emails are registered.
    """
    raw_token = await auth_service.request_password_reset(payload.email)
    if raw_token:
        reset_url = f"{settings.web_app_url}/reset-password?t={raw_token}"
        try:
            email_service.send_password_reset(
                to_email=payload.email,
                reset_url=reset_url,
            )
        except EmailServiceError as exc:
            logger.warning("Password reset email failed: %s", exc)
    return {"sent": True}


@router.post("/password-reset-confirm", response_model=LoginResponse)
async def password_reset_confirm(
    payload: PasswordResetConfirm,
    response: Response,
    auth_service: AuthSvc,
    settings: SettingsDep,
) -> LoginResponse:
    """Complete the password reset and sign the user in."""
    user = await auth_service.confirm_password_reset(
        raw_token=payload.token,
        new_password=payload.new_password,
    )
    _, token, expires_at = await auth_service.authenticate_therapist(
        email=user.email,
        password=payload.new_password,
    )
    _set_session_cookie(response, token, settings)
    return LoginResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        expires_at=expires_at,
    )


@router.post("/verify-email-request", status_code=202)
async def verify_email_request(
    auth_service: AuthSvc,
    email_service: EmailSvc,
    settings: SettingsDep,
    current_user: CurrentTherapist,
) -> dict[str, bool]:
    """Send an email verification link to the currently authenticated user."""
    raw_token = await auth_service.request_email_verification(current_user.id)
    verification_url = f"{settings.web_app_url}/verify-email?t={raw_token}"
    try:
        email_service.send_email_verification(
            to_email=current_user.email,
            verification_url=verification_url,
            therapist_name=current_user.full_name,
        )
    except EmailServiceError as exc:
        logger.warning("Email verification send failed: %s", exc)
    return {"sent": True}


@router.post("/verify-email-confirm", response_model=CurrentUser)
async def verify_email_confirm(
    payload: EmailVerificationConfirm,
    auth_service: AuthSvc,
) -> CurrentUser:
    user = await auth_service.confirm_email_verification(payload.token)
    return CurrentUser.model_validate(user)
