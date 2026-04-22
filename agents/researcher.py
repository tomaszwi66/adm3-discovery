"""
ADM-3 Step 3 - Literature / Prior Art Agent.
Searches the web for each of the top 3 hypotheses and classifies novelty.
"""
import json
import re
import sys

from tools.llm import query_llm
from tools.search import search_web, format_results_for_prompt


def _parse_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


_PROMPT_TEMPLATE = """\
You are the LITERATURE/PRIOR ART AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).

RESEARCH PROBLEM:
{problem}

HYPOTHESES TO EVALUATE:
{hypotheses_json}

WEB SEARCH RESULTS:
{search_results}

YOUR TASK:
Based on the search results, classify each hypothesis:

1. novelty: "Known" | "Partial overlap" | "Likely novel"
   - Known: well-established in literature, multiple sources confirm
   - Partial overlap: some related work exists but this specific framing is new
   - Likely novel: no direct prior art found
2. supporting_evidence: list of 1-3 short quotes or facts from search results that support this
3. contradicting_evidence: list of 1-3 short quotes or facts that contradict this
4. updated_p_correct: revised probability (0-100) incorporating the evidence
5. notes: any important context or caveats

If search results are empty, mark all as "No external verification - high uncertainty" and do NOT change p_correct.

CRITICAL: Output ONLY valid JSON.
{{
  "research": [
    {{
      "id": 1,
      "novelty": "Partial overlap",
      "supporting_evidence": ["..."],
      "contradicting_evidence": ["..."],
      "updated_p_correct": 45,
      "notes": "..."
    }}
  ]
}}
"""


def research(hypotheses: list, problem: str, model: str) -> list:
    """
    Enrich the top 3 hypotheses with web search evidence.
    Returns the full hypothesis list with research fields added to top 3.

    Args:
        hypotheses: filtered list from skeptic (Survives + Weak)
        problem: original research problem string
        model: Ollama model name

    Returns:
        Full list with research annotations merged in.
    """
    if not hypotheses:
        return []

    # Research only the top 3 by p_correct to limit search calls
    top_3 = sorted(hypotheses, key=lambda h: h.get("p_correct", 0), reverse=True)[:3]
    rest = [h for h in hypotheses if h not in top_3]

    # Collect search results for each of the top 3
    all_results_text = []
    for hyp in top_3:
        short_hyp = hyp.get("hypothesis", "")[:80]
        query = f"{problem} {short_hyp}"
        print(f"  [Researcher] Searching: {query[:70]}...", end=" ", flush=True)
        results = search_web(query)
        if results:
            print(f"{len(results)} results.")
        else:
            print("no results.")
        all_results_text.append(f"--- Hypothesis {hyp['id']}: {short_hyp} ---")
        all_results_text.append(format_results_for_prompt(results))

    combined_search = "\n\n".join(all_results_text)
    hyp_json = json.dumps(top_3, indent=2, ensure_ascii=False)

    prompt = _PROMPT_TEMPLATE.format(
        problem=problem,
        hypotheses_json=hyp_json,
        search_results=combined_search,
    )

    print("  [Researcher] Calling LLM for novelty classification...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Researcher] Empty LLM response - skipping research enrichment.", file=sys.stderr)
        for h in hypotheses:
            h.setdefault("novelty", "No external verification - high uncertainty")
        return hypotheses

    parsed = _parse_json(raw)

    if isinstance(parsed, dict) and "research" in parsed:
        research_list = parsed["research"]
        if isinstance(research_list, list):
            research_by_id = {r["id"]: r for r in research_list if isinstance(r, dict)}

            enriched_top3 = []
            for hyp in top_3:
                r = research_by_id.get(hyp["id"], {})
                enriched = {**hyp, **{
                    "novelty": r.get("novelty", "Unknown"),
                    "supporting_evidence": r.get("supporting_evidence", []),
                    "contradicting_evidence": r.get("contradicting_evidence", []),
                    "notes": r.get("notes", ""),
                }}
                # Update p_correct if research provides a new value
                if "updated_p_correct" in r:
                    enriched["p_correct"] = r["updated_p_correct"]
                enriched_top3.append(enriched)

            # Mark unresearched hypotheses
            for h in rest:
                h.setdefault("novelty", "Not researched")

            print(
                f"  [Researcher] Novelty: "
                + ", ".join(
                    f"H{h['id']}={h.get('novelty','?')}" for h in enriched_top3
                )
            )
            return enriched_top3 + rest

    # Fallback
    print("[Researcher WARNING] Could not parse JSON - skipping enrichment.", file=sys.stderr)
    for h in hypotheses:
        h.setdefault("novelty", "No external verification - high uncertainty")
    return hypotheses
