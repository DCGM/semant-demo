"""The caller's own daily LLM allowance."""
from fastapi import APIRouter, Depends

from semant_demo.adapters.sql.quota import MICRO_USD, QuotaLedger
from semant_demo.features.quota import service
from semant_demo.features.quota.principal import get_quota_principal
from semant_demo.features.quota.schemas import QuotaStatusResponse
from semant_demo.features.quota.service import QuotaPolicy, QuotaPrincipal
from semant_demo.routes.dependencies import get_quota_ledger, get_quota_policy

exp_router = APIRouter()


@exp_router.get("/api/quota", response_model=QuotaStatusResponse)
async def get_quota_status(principal: QuotaPrincipal = Depends(get_quota_principal),
                           ledger: QuotaLedger = Depends(get_quota_ledger),
                           policy: QuotaPolicy = Depends(get_quota_policy)) -> QuotaStatusResponse:
    """Today's (UTC) AI usage allowance of the caller: the signed-in account, else the
    guest of the request's cookie (issued when missing). Amounts are estimates."""
    status = await service.status(ledger, policy, principal)
    usd = {name: getattr(status, f"{name}_micro_usd") / MICRO_USD
           for name in ("limit", "used", "charged", "reserved", "remaining")}
    return QuotaStatusResponse(principal=status.principal, day=status.day, reset_at=status.reset_at,
                               near_limit=status.near_limit, exhausted=status.exhausted,
                               **{f"{name}_usd": value for name, value in usd.items()})
