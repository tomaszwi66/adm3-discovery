"""
ADM-3 Step 5 - Ranking Agent.
Scores each surviving hypothesis on Impact, P(correct), TestSpeed,
Scalability, and Robustness. Computes EV = Impact × P(correct) × TestSpeed.
"""
import json
import re
import sys

from tools.llm import query_llm


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
You are the RANKING AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).

RESEARCH PROBLEM:
{problem}

SURVIVING HYPOTHESES (with all prior analysis):
{hypotheses_json}

EXPERIMENT EXECUTION RESULT:
{exec_result}

YOUR TASK:
Score each hypothesis on the following dimensions:

- impact (0-10): scientific/practical significance if proven true
- p_correct (0-100): final calibrated probability after all analysis
- test_speed (0.0-1.0): 1.0 = can be tested in minutes, 0.0 = takes months
- scalability (0-10): how well the finding would scale to broader applications
- robustness (0-10): resistance to confounds, noise, and edge cases
- ev_score: compute as (impact * (p_correct/100.0) * test_speed), rounded to 3 decimal places

Use the experiment result to update p_correct if it provides evidence.
Rank hypotheses from highest to lowest ev_score (rank 1 = best).

CRITICAL: Output ONLY valid JSON.
{{
  "rankings": [
    {{
      "id": 1,
      "impact": 7,
      "p_correct": 45,
      "test_speed": 0.8,
      "scalability": 6,
      "robustness": 7,
      "ev_score": 2.52,
      "rank": 1,
      "ranking_notes": "..."
    }}
  ]
}}
"""


def rank(hypotheses: list, exec_result: dict, model: str) -> list:
    """
    Score and rank all surviving hypotheses.

    Args:
        hypotheses: enriched list from researcher
        exec_result: dict from executor (stdout, success, etc.)
        model: Ollama model name

    Returns:
        List of dicts with ranking scores merged in, sorted by ev_score desc.
    """
    if not hypotheses:
        return []

    # Truncate stdout to avoid massive prompts
    safe_exec = {
        "success": exec_result.get("success", False),
        "stdout": exec_result.get("stdout", "")[:800],
        "stderr": exec_result.get("stderr", "")[:400],
        "timed_out": exec_result.get("timed_out", False),
    } if exec_result else {"success": False, "stdout": "No experiment run.", "stderr": ""}

    hyp_json = json.dumps(hypotheses, indent=2, ensure_ascii=False)
    exec_json = json.dumps(safe_exec, indent=2)

    prompt = _PROMPT_TEMPLATE.format(
        problem="",  # problem not available here; context comes from hypotheses
        hypotheses_json=hyp_json,
        exec_result=exec_json,
    )

    print("  [Ranker] Calling LLM...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Ranker] Empty LLM response - using heuristic ranking.", file=sys.stderr)
        return _heuristic_rank(hypotheses)

    parsed = _parse_json(raw)

    if isinstance(parsed, dict) and "rankings" in parsed:
        rankings = parsed["rankings"]
        if isinstance(rankings, list) and rankings:
            rank_by_id = {r["id"]: r for r in rankings if isinstance(r, dict)}

            merged = []
            for hyp in hypotheses:
                r = rank_by_id.get(hyp["id"], {})
                impact = float(r.get("impact", 5))
                p_c = float(r.get("p_correct", hyp.get("p_correct", 25)))
                speed = float(r.get("test_speed", 0.5))
                ev = round(impact * (p_c / 100.0) * speed, 3)

                merged.append({
                    **hyp,
                    "impact": impact,
                    "p_correct": p_c,
                    "test_speed": speed,
                    "scalability": float(r.get("scalability", 5)),
                    "robustness": float(r.get("robustness", 5)),
                    "ev_score": r.get("ev_score", ev),
                    "ranking_notes": r.get("ranking_notes", ""),
                })

            # Sort by ev_score descending and assign ranks
            merged.sort(key=lambda x: x["ev_score"], reverse=True)
            for i, h in enumerate(merged):
                h["rank"] = i + 1

            print(
                f"  [Ranker] Top hypothesis: H{merged[0]['id']} "
                f"EV={merged[0]['ev_score']} P={merged[0]['p_correct']}%"
            )
            return merged

    print("[Ranker WARNING] Could not parse JSON - using heuristic ranking.", file=sys.stderr)
    return _heuristic_rank(hypotheses)


def _heuristic_rank(hypotheses: list) -> list:
    """Fallback: rank by p_correct alone when LLM fails."""
    sorted_hyps = sorted(
        hypotheses, key=lambda h: h.get("p_correct", 0), reverse=True
    )
    for i, h in enumerate(sorted_hyps):
        p = h.get("p_correct", 25)
        h["ev_score"] = round(p / 100.0 * 5.0 * 0.5, 3)  # heuristic
        h["rank"] = i + 1
        h.setdefault("impact", 5.0)
        h.setdefault("test_speed", 0.5)
        h.setdefault("scalability", 5.0)
        h.setdefault("robustness", 5.0)
    return sorted_hyps
