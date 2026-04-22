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
