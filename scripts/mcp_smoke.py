"""Smoke test of semANT's public MCP endpoint (#635, docs/MCP.md) with the official MCP client.

    .venv/bin/python scripts/mcp_smoke.py [URL] [QUERY]

URL defaults to http://127.0.0.1:8000/mcp (the seeded local application started with
``MCP_ENABLED=true make dev-backend``); QUERY to ``Novák``. Lists the tools, searches passages and
documents, then opens the first hit's document, context and first page with the other three
tools. Prints a short summary of each answer; exits non-zero on any tool error. Read-only.
"""
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

EXPECTED = {"search_passages", "search_documents", "get_document", "get_passage_context", "get_document_page"}


async def main(url: str, query: str) -> None:
    async with streamable_http_client(url) as (read, write, *_):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"server {info.serverInfo.name}, protocol {info.protocolVersion}")
            names = {tool.name for tool in (await session.list_tools()).tools}
            print(f"tools: {sorted(names)}")
            assert names == EXPECTED, names

            async def call(tool: str, **arguments) -> dict:
                result = await session.call_tool(tool, arguments)
                if result.isError:
                    raise SystemExit(f"{tool} failed: {result.content[0].text}")
                return result.structuredContent

            passages = await call("search_passages", query=query, limit=3)
            print(f"search_passages: {len(passages['hits'])} hits of {passages['ranked_count']} ranked "
                  f"(bounded={passages['bounded']}, vector={passages['vector']})")
            documents = await call("search_documents", query=query, limit=3)
            print(f"search_documents: {len(documents['hits'])} hits, eligible {documents['eligible_count']}")
            browse = await call("search_documents", limit=2)
            print(f"search_documents (filters only): next_offset {browse['next_offset']}, total {browse['total_count']}")
            if not passages["hits"]:
                raise SystemExit(f"no passage matches {query!r}; pass another query")
            hit = passages["hits"][0]["passage"]
            document = await call("get_document", document_id=hit["document_id"])
            print(f"get_document: {document['title']!r} ({document['year']}), {document['chunk_count']} passages, "
                  f"{document['page_count']} pages, source {document['source_url']}")
            context = await call("get_passage_context", document_id=hit["document_id"], chunk_id=hit["chunk_id"])
            print(f"get_passage_context: {len(context['passages'])} passages, has_before={context['has_before']}, "
                  f"has_after={context['has_after']}")
            page = await call("get_document_page", document_id=hit["document_id"], page=hit["from_page"])
            print(f"get_document_page {page['page']}: {len(page['passages'])} passages, has_more={page['has_more']}, "
                  f"label {page['page_label']!r}, scans {page['page_scans_available']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp",
                     sys.argv[2] if len(sys.argv) > 2 else "Novák"))
