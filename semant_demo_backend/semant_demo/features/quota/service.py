"""Daily LLM allowances of guests and accounts (#371): status, admission and settlement.

An allowance is a USD-equivalent estimate per UTC calendar day, not a bill. Admission
reserves a bounded estimate of one user-visible AI operation before it starts; once
admitted, the operation runs to its end even when its cost crosses the allowance, and
later operations are refused (``QuotaExhausted``, HTTP 429). Settlement replaces the
reservation with the calls' cost on the operation's start day. An operation that is
never settled (a crash, a lost callback) keeps its reservation charged; nothing expires
or is refunded.

:class:`AllowanceBudget` is the request's allowance as the LLM gateway's operation budget
(``LlmGateway.operation``): AI use cases admit and settle through it (#398).
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from semant_demo.adapters.llm.usage import LlmOperation
from semant_demo.adapters.sql.quota import MICRO_USD, CallRecord, DayTotals, QuotaLedger, usd_to_micro
from semant_demo.config import Config

PrincipalKind = Literal["guest", "account"]


@dataclass(frozen=True)
class QuotaPrincipal:
    """Whose allowance is used: an account UUID, or a hash of the guest cookie."""
    kind: PrincipalKind
    id: str


@dataclass(frozen=True)
class QuotaPolicy:
    guest_daily_micro_usd: int
    account_daily_micro_usd: int
    near_limit_ratio: float
    guest_cookie_max_age_seconds: int
    guest_cookie_secure: bool

    @classmethod
    def from_config(cls, config: Config) -> QuotaPolicy:
        """Raises ``ValueError`` for a non-positive allowance or cookie lifetime, or a
        near-limit ratio outside (0, 1]."""
        allowances = (config.LLM_QUOTA_GUEST_DAILY_USD, config.LLM_QUOTA_ACCOUNT_DAILY_USD)
        if not all(0 < usd < float("inf") for usd in allowances):
            raise ValueError("LLM_QUOTA_GUEST_DAILY_USD and LLM_QUOTA_ACCOUNT_DAILY_USD must be positive")
        if not 0 < config.LLM_QUOTA_NEAR_LIMIT_RATIO <= 1:
            raise ValueError("LLM_QUOTA_NEAR_LIMIT_RATIO must be in (0, 1]")
        if config.LLM_QUOTA_GUEST_COOKIE_DAYS <= 0:
            raise ValueError("LLM_QUOTA_GUEST_COOKIE_DAYS must be positive")
        return cls(guest_daily_micro_usd=usd_to_micro(config.LLM_QUOTA_GUEST_DAILY_USD),
                   account_daily_micro_usd=usd_to_micro(config.LLM_QUOTA_ACCOUNT_DAILY_USD),
                   near_limit_ratio=config.LLM_QUOTA_NEAR_LIMIT_RATIO,
                   guest_cookie_max_age_seconds=config.LLM_QUOTA_GUEST_COOKIE_DAYS * 24 * 60 * 60,
                   guest_cookie_secure=config.LLM_QUOTA_GUEST_COOKIE_SECURE)

    def daily_limit(self, principal: QuotaPrincipal) -> int:
        return self.account_daily_micro_usd if principal.kind == "account" else self.guest_daily_micro_usd


@dataclass(frozen=True)
class QuotaStatus:
    principal: PrincipalKind
    day: str
    limit_micro_usd: int
    reserved_micro_usd: int
    charged_micro_usd: int
    reset_at: datetime.datetime
    near_limit: bool
    exhausted: bool

    @property
    def used_micro_usd(self) -> int:
        return self.reserved_micro_usd + self.charged_micro_usd

    @property
    def remaining_micro_usd(self) -> int:
        return max(self.limit_micro_usd - self.used_micro_usd, 0)


class QuotaExhausted(Exception):
    """The principal's remaining daily allowance has no room for an AI operation (HTTP 429):
    the allowance is used up, or the operation's reservation exceeds what is left."""

    code = "llm_quota_exhausted"

    def __init__(self, status: QuotaStatus):
        super().__init__("Insufficient remaining daily AI allowance for this operation; it resets at "
                         f"{status.reset_at:%Y-%m-%d %H:%M} UTC.")
        self.status = status

    def body(self) -> dict:
        return {"detail": str(self), "code": self.code, "principal": self.status.principal,
                "reset_at": self.status.reset_at.isoformat(), "limit_usd": self.status.limit_micro_usd / MICRO_USD,
                "used_usd": self.status.used_micro_usd / MICRO_USD}

    def retry_after_seconds(self, now: datetime.datetime) -> int:
        return max(int((self.status.reset_at - now).total_seconds()) + 1, 1)


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utc_day(now: datetime.datetime) -> str:
    return now.astimezone(datetime.timezone.utc).date().isoformat()


def next_reset(now: datetime.datetime) -> datetime.datetime:
    today = now.astimezone(datetime.timezone.utc).date()
    return datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time(), datetime.timezone.utc)


def _status(policy: QuotaPolicy, principal: QuotaPrincipal, totals: DayTotals,
            now: datetime.datetime) -> QuotaStatus:
    limit = policy.daily_limit(principal)
    return QuotaStatus(principal=principal.kind, day=utc_day(now), limit_micro_usd=limit,
                       reserved_micro_usd=totals.reserved_micro_usd, charged_micro_usd=totals.charged_micro_usd,
                       reset_at=next_reset(now), near_limit=totals.used_micro_usd >= policy.near_limit_ratio * limit,
                       exhausted=totals.used_micro_usd >= limit)


async def status(ledger: QuotaLedger, policy: QuotaPolicy, principal: QuotaPrincipal,
                 now: datetime.datetime | None = None) -> QuotaStatus:
    """The principal's allowance today (UTC); only its own, there is no lookup of others."""
    now = now or utc_now()
    return _status(policy, principal, await ledger.totals(principal.kind, principal.id, utc_day(now)), now)


async def admit(ledger: QuotaLedger, policy: QuotaPolicy, principal: QuotaPrincipal, feature: str,
                reserve_usd: float, now: datetime.datetime | None = None) -> str:
    """Reserve ``reserve_usd`` (a bounded upper estimate of the operation) and return the
    operation id to settle. Raises ``QuotaExhausted`` when the day's allowance is used up
    or the used amount and the reservation would exceed it; nothing is reserved then."""
    if not 0 <= reserve_usd < float("inf"):
        raise ValueError("A quota reservation must be a finite non-negative amount")
    now = now or utc_now()
    admission = await ledger.admit(principal.kind, principal.id, utc_day(now), feature=feature,
                                   reserve_micro_usd=usd_to_micro(reserve_usd),
                                   limit_micro_usd=policy.daily_limit(principal), now=now)
    if admission.operation_id is None:
        raise QuotaExhausted(_status(policy, principal, admission.totals, now))
    return admission.operation_id


async def settle(ledger: QuotaLedger, operation_id: str, calls: list[CallRecord],
                 now: datetime.datetime | None = None) -> int | None:
    """Charge the operation's calls to its start day (see ``QuotaLedger.settle``)."""
    return await ledger.settle(operation_id, calls, now=now or utc_now())


@dataclass(frozen=True)
class AllowanceBudget:
    """A principal's daily allowance as an ``OperationBudget`` of the LLM gateway.

    ``admit`` raises ``QuotaExhausted`` before any model call. ``settle`` records the
    operation's finished calls; a call that was still running counts as one of unknown
    cost, so the operation is charged at least its reservation.
    """
    ledger: QuotaLedger
    policy: QuotaPolicy
    principal: QuotaPrincipal
    clock: Callable[[], datetime.datetime] = utc_now

    async def admit(self, feature: str, reserve_usd: float) -> str:
        return await admit(self.ledger, self.policy, self.principal, feature, reserve_usd, now=self.clock())

    async def settle(self, admission: str, operation: LlmOperation) -> None:
        calls = [CallRecord(feature=c.feature, tier=str(c.model.tier), provider=str(c.model.provider),
                            model=c.model.model, outcome=c.outcome, usage_source=c.usage_source,
                            cost_source=c.cost_source, cost_usd=c.cost_usd, input_tokens=c.input_tokens,
                            output_tokens=c.output_tokens) for c in operation.calls]
        unfinished = max(operation.started_calls - len(operation.calls), 0)
        calls += [CallRecord(feature=operation.feature, tier="", provider="", model="", outcome="unfinished",
                             usage_source="unavailable", cost_source="unknown", cost_usd=None)] * unfinished
        await settle(self.ledger, admission, calls, now=self.clock())
