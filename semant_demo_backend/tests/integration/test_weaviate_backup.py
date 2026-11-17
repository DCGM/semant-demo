"""deploy/weaviate_backup.py (#469) against a real ``backup-filesystem`` Weaviate: the REST calls
of a full and an incremental backup, a restore of the incremental backup (through its base)
with matching counts, and the read-only ``counts`` used by the restore rehearsal.

The backups stay inside the throwaway container, so the on-disk part (chains, retention, free
space) is covered by the fast tests in tests/test_weaviate_backup_script.py.
"""
import uuid

import pytest
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.tenants import Tenant, TenantActivityStatus

from tests.test_weaviate_backup_script import wb
from tests.weaviate_store import claim_store

pytestmark = pytest.mark.integration

PLAIN, TENANTS = "BackupProbe469", "BackupProbeTenants469"


@pytest.fixture
async def probe(weaviate_client, store_token):
    await claim_store(weaviate_client, store_token)
    for name in (PLAIN, TENANTS):
        await weaviate_client.collections.delete(name)
    plain = await weaviate_client.collections.create(
        PLAIN, properties=[Property(name="text", data_type=DataType.TEXT)],
        vector_config=Configure.Vectors.self_provided())
    tenants = await weaviate_client.collections.create(
        TENANTS, properties=[Property(name="text", data_type=DataType.TEXT)],
        vector_config=Configure.Vectors.self_provided(),
        multi_tenancy_config=Configure.multi_tenancy(enabled=True))
    await tenants.tenants.create([Tenant(name="active"), Tenant(name="cold")])
    yield plain, tenants
    for name in (PLAIN, TENANTS):
        await weaviate_client.collections.delete(name)


async def insert(collection, start, count, vector_size=4):
    for i in range(start, start + count):
        await collection.data.insert({"text": f"object {i}"}, vector=[float(i % 7), 1.0, 0.5, 0.25][:vector_size])


def api_for(store_endpoint):
    return wb.Weaviate(f"http://{store_endpoint.host}:{store_endpoint.rest_port}")


async def set_cold(tenants, cold: bool):
    status = TenantActivityStatus.INACTIVE if cold else TenantActivityStatus.ACTIVE
    await tenants.tenants.update([Tenant(name="cold", activity_status=status)])


async def cold_status(tenants):
    return (await tenants.tenants.get_by_name("cold")).activity_status


def probe_counts(api, activate_inactive=False):
    return {k: v for k, v in api.counts(activate_inactive).items() if "Probe" in k}


def restore_test_backup(api, backup_id, settings):
    """Restore through the REST API directly: the store is disposable (``claim_store``), but
    CI reaches it as ``weaviate:8080``, which the operator-facing ``run_restore`` guard refuses
    (that guard is unit-tested in tests/test_weaviate_backup_script.py)."""
    api.restore(backup_id, include=[PLAIN, TENANTS])
    return wb.wait_for(lambda: api.restore_status(backup_id), settings, f"restore of {backup_id}")


async def test_full_and_incremental_backups_restore_with_matching_counts(probe, weaviate_client, store_endpoint):
    plain, tenants = probe
    api = api_for(store_endpoint)
    settings = wb.Settings(poll_seconds=0.2)
    run = uuid.uuid4().hex[:8]
    full, incr = f"probe469-{run}-full", f"probe469-{run}-incr"
    await insert(plain, 0, 30)
    await insert(tenants.with_tenant("active"), 0, 5)
    await insert(tenants.with_tenant("cold"), 0, 3)
    await set_cold(tenants, True)

    api.create(full, include=[PLAIN, TENANTS])
    assert wb.wait_for(lambda: api.status(full), settings, full)["status"] == "SUCCESS"
    await insert(plain, 30, 20)
    await insert(tenants.with_tenant("active"), 5, 2)
    await set_cold(tenants, False)
    await insert(tenants.with_tenant("cold"), 3, 1)  # the inactive tenant also changes between backups
    await set_cold(tenants, True)
    api.create(incr, base=full, include=[PLAIN, TENANTS])
    assert wb.wait_for(lambda: api.status(incr), settings, incr)["status"] == "SUCCESS"

    # Read-only counts list an inactive tenant by status; --activate-inactive counts its
    # objects and sets it back to inactive.
    assert probe_counts(api) == {PLAIN: 50, f"{TENANTS}/active": 7, f"{TENANTS}/cold": "COLD"}
    before = probe_counts(api, activate_inactive=True)
    assert before == {PLAIN: 50, f"{TENANTS}/active": 7, f"{TENANTS}/cold": "COLD 4"}
    assert await cold_status(tenants) == TenantActivityStatus.INACTIVE

    for name in (PLAIN, TENANTS):
        await weaviate_client.collections.delete(name)
    restored = restore_test_backup(api, incr, settings)

    assert restored["status"] == "SUCCESS"
    assert probe_counts(api, activate_inactive=True) == before
    assert await cold_status(tenants) == TenantActivityStatus.INACTIVE

    # The base alone still restores the state it was taken in.
    for name in (PLAIN, TENANTS):
        await weaviate_client.collections.delete(name)
    assert restore_test_backup(api, full, settings)["status"] == "SUCCESS"
    assert probe_counts(api, activate_inactive=True) == {
        PLAIN: 30, f"{TENANTS}/active": 5, f"{TENANTS}/cold": "COLD 3"}


async def test_an_incremental_backup_on_a_missing_base_is_refused(probe, store_endpoint):
    api = api_for(store_endpoint)
    with pytest.raises(wb.BackupError, match="HTTP 4"):
        api.create(f"probe469-{uuid.uuid4().hex[:8]}-orphan", base="probe469-does-not-exist", include=[PLAIN])
