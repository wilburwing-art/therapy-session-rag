"""Billing Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CheckoutSessionResponse(BaseModel):
    url: str


class PortalSessionResponse(BaseModel):
    url: str


class SubscriptionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subscription_status: str
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None
    has_stripe_customer: bool
    is_entitled: bool


class BillingUsageResponse(BaseModel):
    """Current-period usage counters plus seat utilisation."""

    model_config = ConfigDict(from_attributes=True)

    period_start: datetime
    period_end: datetime
    sessions_transcribed: int
    recaps_generated: int
    chat_messages: int
    seats_used: int
    seats_included: int


class UpcomingInvoiceResponse(BaseModel):
    """Preview of the next Stripe invoice."""

    amount_due: int
    amount_total: int
    currency: str
    period_end: datetime | None = None
