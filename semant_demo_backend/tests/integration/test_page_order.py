"""Start-page check of the page-order export (#571) against the real test store: every chunk
is read with keyset paging, past the former 1,000-chunk limit."""
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate.document_metadata import IncompleteRead, iter_start_pages
from semant_demo.maintenance.page_order import weaviate_start_page_checker

pytestmark = pytest.mark.integration

PAGES = {UUID(int=0x9A6E0000 + p) for p in range(10)}
FOREIGN = UUID(int=0x9A6EFFFF)


async def add_document(store, names, number: int, orders: list[int | None], start_pages: list[str]) -> UUID:
    document = UUID(int=0x5E7A0000 + number)
    await store.collections.get(names.document_collection_name).data.insert(uuid=document, properties={})
    chunks = store.collections.get(names.chunks_collection_name)
    for first in range(0, len(orders), 1000):
        result = await chunks.data.insert_many([
            DataObject(uuid=UUID(int=document.int * 10_000 + i),
                       properties={"text": f"chunk {i}", "start_page_id": start_pages[i],
                                   **({"order": orders[i]} if orders[i] is not None else {})},
                       references={"document": document})
            for i in range(first, min(len(orders), first + 1000))])
        assert not result.errors
    return document


async def test_all_chunks_are_checked_past_the_former_limit(seeded_store, collection_names):
    pages = sorted(map(str, PAGES))
    size = 2_345
    clean = await add_document(seeded_store, collection_names, 1, list(range(size)),
                               [pages[i % 10] for i in range(size)])
    late = await add_document(seeded_store, collection_names, 2, list(range(size)),
                              [pages[i % 10] if i != 2_000 else str(FOREIGN) for i in range(size)])
    checker = weaviate_start_page_checker(seeded_store, collection_names)

    passing = await checker(clean, PAGES)
    assert (passing.chunks, passing.foreign.count, passing.invalid.count, passing.error) == (size, 0, 0, None)
    conflict = await checker(late, PAGES)
    assert (conflict.chunks, conflict.foreign.count, conflict.error) == (size, 1, None)
    assert conflict.foreign.values == {str(FOREIGN)}

    batches = [len(b) async for b in iter_start_pages(seeded_store, collection_names, clean, page_size=1000)]
    assert sum(batches) == size and len(batches) == 3 and max(batches) <= 1000


async def test_tied_orders_across_a_page_boundary_are_read_once(seeded_store, collection_names):
    orders = [0, 1, 2, 3, 3, 3, 4, 5, 6, 6, 7]
    document = await add_document(seeded_store, collection_names, 3, orders, [str(FOREIGN)] * len(orders))
    read = [v async for b in iter_start_pages(seeded_store, collection_names, document, page_size=5) for v in b]
    assert len(read) == len(orders)


async def test_a_partial_read_is_reported_not_passed(seeded_store, collection_names):
    no_order = await add_document(seeded_store, collection_names, 4, [0, None, 2], [str(min(PAGES))] * 3)
    ties = await add_document(seeded_store, collection_names, 5, [1] * 6, [str(min(PAGES))] * 6)
    with pytest.raises(IncompleteRead):
        async for _ in iter_start_pages(seeded_store, collection_names, ties, page_size=4):
            pass
    check = await weaviate_start_page_checker(seeded_store, collection_names)(no_order, PAGES)
    assert check.error is not None and check.error.startswith("IncompleteRead")
