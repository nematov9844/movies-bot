"""Abstract interface for premium payment gateways.

No concrete implementation exists yet. Phase 8 only wires the manual,
support-mediated flow (an admin grants premium by hand after the user pays
out-of-band — see ``app/bot/handlers/user/premium.py`` and
``app/bot/handlers/admin/premium_grant.py``). This class sketches the
contract a real integration would implement so one can be dropped in later
— Click, Payme, Uzum Bank, or Telegram Stars are the obvious candidates for
the Uzbek market this bot targets — without reshaping ``PremiumService`` or
the handlers around it.

A future concrete provider is expected to be composed into the purchase
flow roughly as: ``create_payment`` gives the user something to pay
against (a checkout URL, an invoice payload, ...), and once the provider
confirms the payment (webhook or polling), ``verify_payment`` is checked
before calling ``PremiumService.grant``.
"""

from abc import ABC, abstractmethod

from app.database.models import PremiumPlan


class PaymentProvider(ABC):
    """One payment gateway integration: start a payment, then verify it."""

    @abstractmethod
    async def create_payment(self, user_id: int, plan: PremiumPlan) -> str:
        """Start a payment for ``plan`` on behalf of ``user_id``.

        Returns a provider-specific payment URL or reference that the user
        is sent to in order to complete the transaction.
        """
        raise NotImplementedError

    @abstractmethod
    async def verify_payment(self, payment_reference: str) -> bool:
        """Whether the payment identified by ``payment_reference`` has completed successfully."""
        raise NotImplementedError
