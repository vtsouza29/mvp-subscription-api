"""Vocabulary of the subscription domain.

`SpendCategory` and `BillingCycle` are shared with the budget service and must
stay in sync with it: they cross the wire on every call.
"""

from enum import Enum


class SpendCategory(str, Enum):
    """Category a recurring expense belongs to."""

    STREAMING = "STREAMING"
    SAAS = "SAAS"
    GAMING = "GAMING"
    EDUCATION = "EDUCATION"
    HEALTH = "HEALTH"
    OTHER = "OTHER"


class BillingCycle(str, Enum):
    """How often a subscription is charged."""

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"

    @property
    def month_step(self) -> int:
        """Number of months between two consecutive charges."""
        return {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}[self.value]


class SubscriptionStatus(str, Enum):
    """Lifecycle of a subscription."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
