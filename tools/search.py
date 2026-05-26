"""
Web search tool with configurable provider (DuckDuckGo or Tavily).
Returns a list of {title, body, href} dicts.
Falls back to an empty list on any error - never crashes the pipeline.
"""
import sys

import config


def _search_duckduckgo(query: str, max_results: int) -> list:
    """Search via DuckDuckGo."""
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


def _search_tavily(query: str, max_results: int) -> list:
    """Search via Tavily."""
    try:
        from tavily import TavilyClient
    except ImportError:
        print(
            "[SEARCH WARNING] tavily-python not installed. "
            "Run: pip install tavily-python",
            file=sys.stderr,
        )
        return []

    api_key = config.TAVILY_API_KEY
    if not api_key:
        print(
            "[SEARCH WARNING] TAVILY_API_KEY not set. "
            "Export the env var or add it to your environment.",
            file=sys.stderr,
        )
        return []

    results = []
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        for r in response.get("results", []):
            results.append(
                {
                    "title": r.get("title", ""),
                    "body": r.get("content", ""),
                    "href": r.get("url", ""),
                }
            )
    except Exception as exc:
        print(f"[SEARCH WARNING] Tavily search failed: {exc}", file=sys.stderr)

    return results


def search_web(query: str, max_results: int = None) -> list:
    """
    Search the web and return up to max_results results.

    The backend is selected by config.SEARCH_PROVIDER:
      - 'duckduckgo' (default): uses the ddgs library
      - 'tavily': uses the tavily-python client

    Returns:
        list of dicts: [{title: str, body: str, href: str}, ...]
        Empty list if the search fails or the library is unavailable.
    """
    max_results = max_results or config.SEARCH_RESULTS

    provider = config.SEARCH_PROVIDER.lower()
    if provider == "tavily":
        return _search_tavily(query, max_results)
    return _search_duckduckgo(query, max_results)


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
