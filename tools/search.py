"""
Configurable web search tool (DuckDuckGo by default).
Returns a list of {title, body, href} dicts.
Falls back to an empty list on any error - never crashes the pipeline.
"""
import asyncio
import sys

import config


def search_web(query: str, max_results: int = None) -> list:
    """
    Search with the configured provider and return up to max_results results.

    Returns:
        list of dicts: [{title: str, body: str, href: str}, ...]
        Empty list if the search fails or the library is unavailable.
    """
    max_results = config.SEARCH_RESULTS if max_results is None else max_results
    if max_results <= 0 or config.SEARCH_PROVIDER == "none":
        return []
    if config.SEARCH_PROVIDER == "parallel":
        try:
            from tools.parallel_search import search_parallel
        except ImportError:
            print(
                "[SEARCH WARNING] Parallel dependencies not installed. "
                "Run: pip install -r requirements-parallel.txt",
                file=sys.stderr,
            )
            return []
        try:
            return asyncio.run(search_parallel(query, max_results))
        except asyncio.TimeoutError:
            print("[SEARCH WARNING] Parallel search timed out.", file=sys.stderr)
        except Exception as exc:
            print(f"[SEARCH WARNING] Parallel search failed: {exc}", file=sys.stderr)
        return []
    if config.SEARCH_PROVIDER != "duckduckgo":
        print(
            f"[SEARCH WARNING] Unknown search provider: {config.SEARCH_PROVIDER}",
            file=sys.stderr,
        )
        return []

    return _search_duckduckgo(query, max_results)


def _search_duckduckgo(query: str, max_results: int) -> list:

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        print(
            "[SEARCH WARNING] Search library not installed. "
            "Run: pip install ddgs",
            file=sys.stderr,
        )
        return []

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "body": r.get("body", ""),
                        "href": r.get("href", ""),
                    }
                )
    except Exception as exc:
        print(f"[SEARCH WARNING] DuckDuckGo search failed: {exc}", file=sys.stderr)

    return results


def format_results_for_prompt(results: list) -> str:
    """
    Convert a list of search result dicts into a concise string
    suitable for embedding in an LLM prompt.
    """
    if not results:
        return "No search results available - high uncertainty."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        body = r.get("body", "")[:300]
        href = r.get("href", "")
        lines.append(f"[{i}] {title}\n    {body}\n    Source: {href}")
    return "\n\n".join(lines)
