"""Anonymous Parallel Search MCP adapter for the synchronous research pipeline."""
import asyncio
import json
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import config


MCP_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "adm3-discovery (+https://github.com/tomaszwi66/adm3-discovery)"
# One discovery CLI process is one research session, shared across hypotheses/cycles.
_SESSION_ID = str(uuid4())


async def search_parallel(query: str, max_results: int) -> list:
    """Bound the complete handshake/discovery/search operation, including cleanup."""
    return await asyncio.wait_for(_search(query, max_results), config.SEARCH_TIMEOUT)


async def _search(query: str, max_results: int) -> list:
    timeout = timedelta(seconds=config.SEARCH_TIMEOUT)
    async with streamablehttp_client(
        MCP_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        sse_read_timeout=timeout,
    ) as (read, write, _):
        async with ClientSession(read, write, read_timeout_seconds=timeout) as session:
            await session.initialize()
            tools = await session.list_tools()
            if not any(tool.name == "web_search" for tool in tools.tools):
                raise ValueError("Parallel MCP did not advertise web_search")
            result = await session.call_tool(
                "web_search",
                {"objective": query, "search_queries": [query], "session_id": _SESSION_ID},
            )

    if result.isError:
        message = " ".join(
            block.text for block in result.content if block.type == "text"
        )
        raise ValueError(message or "Parallel MCP returned a tool error")

    payload = result.structuredContent
    if payload is None:
        # MCP clients/servers may supply JSON as text without structuredContent.
        text = "\n".join(block.text for block in result.content if block.type == "text")
        payload = json.loads(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Parallel MCP returned an invalid search response")

    results = []
    for item in payload["results"]:
        if not isinstance(item, dict):
            raise ValueError("Parallel MCP returned an invalid search result")
        url, excerpts = item.get("url"), item.get("excerpts")
        if not isinstance(url, str) or not isinstance(excerpts, list):
            raise ValueError("Parallel MCP result is missing its URL or excerpts")
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ValueError("Parallel MCP returned a non-HTTP source URL")
        if not all(isinstance(excerpt, str) for excerpt in excerpts):
            raise ValueError("Parallel MCP returned invalid excerpts")
        title = item.get("title") or url
        if not isinstance(title, str):
            raise ValueError("Parallel MCP returned an invalid title")
        results.append({"title": title, "body": "\n".join(excerpts), "href": url})
        if len(results) >= max_results:
            break
    return results
