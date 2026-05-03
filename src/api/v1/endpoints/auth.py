"""Therapist and patient authentication endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from src.api.v1.dependencies import CurrentPatient, CurrentTherapist, Events
from src.core.config import Settings, get_settings
from src.core.csrf import (
    clear_csrf_cookie,
    new_csrf_token,
    set_csrf_cookie,
)
from src.core.database import DbSession
from src.core.exceptions import RateLimitError
from src.models.db.event import EventCategory
from src.models.domain.auth import (
    Challenge2FARequest,
    CurrentUser,
    Disable2FARequest,
    EmailVerificationConfirm,
    Enroll2FAResponse,
    LoginChallengeResponse,
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
    Verify2FARequest,
)
from src.models.domain.auth import (
    CurrentPatient as CurrentPatientSchema,
)
from src.services.auth_service import AuthService
from src.services.email_service import EmailService, EmailServiceError
from src.services.magic_link_service import MagicLinkService
from src.services.rate_limiter import AuthRateLimiter, RateLimitExceeded
from src.services.totp_service import TotpService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(session)


def get_magic_link_service(session: DbSession) -> MagicLinkService:
    return MagicLinkService(session)


def get_email_service() -> EmailService:
    return EmailService()


def get_totp_service(session: DbSession) -> TotpService:
    return TotpService(session)


def get_auth_rate_limiter() -> AuthRateLimiter:
    """Redis-backed per-IP/email rate limits for auth endpoints."""
    return AuthRateLimiter()


AuthSvc = Annotated[AuthService, Depends(get_auth_service)]
MagicLinkSvc = Annotated[MagicLinkService, Depends(get_magic_link_service)]
EmailSvc = Annotated[EmailService, Depends(get_email_service)]
TotpSvc = Annotated[TotpService, Depends(get_totp_service)]
AuthLimiter = Annotated[AuthRateLimiter, Depends(get_auth_rate_limiter)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
PATIENT_COOKIE_NAME = "therapyrag_patient"


def _client_ip(request: Request) -> str:
    """Extract the client IP, tolerating missing/proxied cases."""
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


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


@router.post("/login", response_model=None)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthSvc,
    rate_limiter: AuthLimiter,
    settings: SettingsDep,
    events: Events,
) -> LoginResponse | LoginChallengeResponse:
    """Authenticate a therapist and either set a JWT session cookie or
    start a 2FA challenge.

    The return body is either `LoginResponse` (no 2FA, session cookie
    set) or `LoginChallengeResponse` (2FA required, no cookie set yet
    — client must POST /auth/2fa/challenge next). Both are HTTP 200 so
    the fetch layer doesn't need an error branch; the client inspects
    `requires_2fa` to decide what to do.
    """
    try:
        await rate_limiter.check_login(_client_ip(request), payload.email)
    except RateLimitExceeded as exc:
        raise RateLimitError(detail=str(exc), retry_after=exc.reset_time) from exc

    user, token, expires_at, requires_2fa = await auth_service.authenticate_therapist(
        email=payload.email,
        password=payload.password,
    )
    if requires_2fa:
        return LoginChallengeResponse(
            challenge_token=token,
            expires_at=expires_at,
        )

    _set_session_cookie(response, token, settings)

    # Stamp the successful login. The access-review CLI looks for the
    # most recent instance of this event per user to compute last-login.
    await events.publish(
        event_name="auth.login_succeeded",
        category=EventCategory.USER_ACTION,
        organization_id=user.organization_id,
        actor_id=user.id,
        properties={
            "role": user.role.value,
            "ip": _client_ip(request),
        },
    )

    return LoginResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        expires_at=expires_at,
    )


@router.post("/2fa/challenge", response_model=LoginResponse)
async def complete_2fa_challenge(
    payload: Challenge2FARequest,
    request: Request,
    response: Response,
    auth_service: AuthSvc,
    settings: SettingsDep,
    events: Events,
) -> LoginResponse:
    """Complete a 2FA login by verifying a TOTP code against the
    challenge token issued during /auth/login."""
    user, token, expires_at = await auth_service.complete_totp_challenge(
        challenge_token=payload.challenge_token,
        code=payload.code,
    )
    _set_session_cookie(response, token, settings)

    # Mirror the non-2FA branch so the access-review CLI's "most recent
    # login" query catches 2FA-gated accounts too.
    await events.publish(
        event_name="auth.login_succeeded",
        category=EventCategory.USER_ACTION,
        organization_id=user.organization_id,
        actor_id=user.id,
        properties={
            "role": user.role.value,
            "ip": _client_ip(request),
            "two_factor": True,
        },
    )

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
    request: Request,
    response: Response,
    auth_service: AuthSvc,
    email_service: EmailSvc,
    rate_limiter: AuthLimiter,
    settings: SettingsDep,
) -> RegisterResponse:
    """Create a new practice (org) plus its founding therapist account.

    The caller is automatically logged in on success. Email is lowercased
    and must be unique across all users. Passwords must be at least 8
    characters. A verification email is dispatched immediately after
    account creation (best-effort — a send failure does not fail the
    signup).
    """
    try:
        await rate_limiter.check_registration(_client_ip(request))
    except RateLimitExceeded as exc:
        raise RateLimitError(detail=str(exc), retry_after=exc.reset_time) from exc

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
        logger.warning("Failed to email magic link to %s: %s", patient.email, exc)

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
    rate_limiter: AuthLimiter,
    settings: SettingsDep,
) -> dict[str, bool]:
    """Send a password-reset email if the address matches an account.

    Always returns 202 with `sent: true` regardless of whether the
    user exists, to avoid leaking which emails are registered.
    """
    try:
        await rate_limiter.check_password_reset(payload.email)
    except RateLimitExceeded as exc:
        raise RateLimitError(detail=str(exc), retry_after=exc.reset_time) from exc

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
    _, token, expires_at, _ = await auth_service.authenticate_therapist(
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


@router.post("/2fa/enroll", response_model=Enroll2FAResponse)
async def enroll_2fa(
    totp_service: TotpSvc,
    current_user: CurrentTherapist,
) -> Enroll2FAResponse:
    """Start enrollment — return provisioning URI + raw secret.

    Idempotent against abandoned enrollments: calling twice before
    activation replaces the pending secret. Returns 409 if 2FA is
    already active (must disable first).
    """
    provisioning_uri, raw_secret = await totp_service.enroll(current_user.id)
    return Enroll2FAResponse(
        provisioning_uri=provisioning_uri,
        secret=raw_secret,
    )


@router.post("/2fa/activate", status_code=200)
async def activate_2fa(
    payload: Verify2FARequest,
    totp_service: TotpSvc,
    current_user: CurrentTherapist,
) -> dict[str, bool]:
    """Verify the enrollment code and activate 2FA on the account."""
    await totp_service.activate(current_user.id, payload.code)
    return {"enabled": True}


@router.post("/2fa/disable", status_code=200)
async def disable_2fa(
    payload: Disable2FARequest,
    totp_service: TotpSvc,
    current_user: CurrentTherapist,
    events: Events,
) -> dict[str, bool]:
    """Disable 2FA after verifying the current password AND a TOTP code.

    Requires both factors so a stolen session cookie alone can't
    remove 2FA — the attacker would also need the authenticator.
    """
    # Local imports to keep the auth core surface small.
    from src.core.auth import verify_password
    from src.core.exceptions import UnauthorizedError

    if current_user.password_hash is None or not verify_password(
        payload.password, current_user.password_hash
    ):
        raise UnauthorizedError("Invalid password")

    await totp_service.disable(current_user.id, payload.code)

    # SOC 2 CC6.6: disabling MFA is a material auth-posture change.
    # Flagged retain_forever so the audit survives the retention purge.
    await events.publish(
        event_name="auth.2fa_disabled",
        category=EventCategory.USER_ACTION,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        retain_forever=True,
    )

    return {"enabled": False}
