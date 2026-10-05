"""Provider boundary. Only the explicitly marked local sandbox is implemented."""
from dataclasses import dataclass
from typing import Protocol, Mapping

@dataclass(frozen=True)
class PaymentIntent:
    provider: str
    amount_minor: int
    currency: str
    idempotency_key: str
    checkout_url: str | None = None

@dataclass(frozen=True)
class VerifiedPaymentEvent:
    provider_reference: str
    order_reference: str
    amount_minor: int
    currency: str
    status: str

class PaymentProvider(Protocol):
    name: str
    def create_intent(self, order_id: str, amount_minor: int, currency: str, idempotency_key: str) -> PaymentIntent: ...
    def verify_webhook(self, headers: Mapping[str, str], raw_body: bytes) -> VerifiedPaymentEvent: ...
    def refund(self, provider_reference: str, amount_minor: int, idempotency_key: str) -> str: ...

class DevelopmentSandboxProvider:
    name='sandbox'
    def create_intent(self, order_id, amount_minor, currency, idempotency_key):
        return PaymentIntent(self.name,amount_minor,currency,idempotency_key)
    def verify_webhook(self, headers, raw_body):
        raise RuntimeError('The local sandbox does not accept external webhooks.')
    def refund(self, provider_reference, amount_minor, idempotency_key):
        raise RuntimeError('Sandbox purchases have no external funds to refund.')

class UnavailableProvider:
    name='disabled'
    def create_intent(self, order_id, amount_minor, currency, idempotency_key):
        raise RuntimeError('No live payment provider adapter is configured.')
    def verify_webhook(self, headers, raw_body):
        raise RuntimeError('No live payment provider adapter is configured.')
    def refund(self, provider_reference, amount_minor, idempotency_key):
        raise RuntimeError('No live payment provider adapter is configured.')

def get_provider(mode: str, configured_name: str = 'disabled') -> PaymentProvider:
    if mode=='development' and configured_name in ('disabled','sandbox'):
        return DevelopmentSandboxProvider()
    # Explicit credentials alone must never make the application report a provider as operational.
    raise RuntimeError('The configured payment provider has no implemented, verified adapter.')
