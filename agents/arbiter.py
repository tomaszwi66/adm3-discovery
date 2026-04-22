"""
ADM-3 Step 6 - Arbiter Agent.
Resolves contradictions between all prior agents.
Issues a binding decision with the best-bet hypothesis, 7/30-day roadmap,
and memory pattern updates.
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


def _summarise_hypotheses(ranked: list) -> str:
    """Create a compact summary of ranked hypotheses for the prompt."""
    lines = []
    for h in ranked[:5]:  # top 5 only to limit prompt size
        lines.append(
            f"  H{h['id']} [Rank {h.get('rank','?')}] EV={h.get('ev_score','?')} "
            f"P={h.get('p_correct','?')}% "
            f"Novelty={h.get('novelty','?')} "
            f"Class={h.get('classification','?')}\n"
            f"    Hyp: {h.get('hypothesis','')[:120]}"
        )
    return "\n".join(lines)


_PROMPT_TEMPLATE = """\
You are the ARBITER AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).
Your decision is BINDING and FINAL.

RESEARCH PROBLEM:
{problem}

RANKED HYPOTHESES SUMMARY:
{ranked_summary}

EXPERIMENT RESULT:
{exec_result}

YOUR TASK:
1. Review all evidence: skeptic analysis, research novelty, experiment results, EV rankings
2. Resolve any contradictions between agents
3. Select the single BEST BET hypothesis that maximises: EV score × empirical support × testability
4. Provide justification weighing all evidence (3-5 sentences)
5. Note any strong dissenting views (hypotheses that nearly won)
6. Define immediate next actions: 3 specific steps for the next 7 days, 3 steps for 30 days
7. Extract memory patterns: what recurring patterns, successful strategies, or rejected biases
   should be saved to improve future runs?

Prioritise fast-falsifiable hypotheses over elegant theories.
If the experiment contradicts the top-ranked hypothesis, adjust accordingly.

CRITICAL: Output ONLY valid JSON.
{{
  "arbiter_decision": {{
    "winner_id": 2,
    "final_p_correct": 55,
    "justification": "...",
    "dissenting_views": [
      {{"id": 3, "p_correct": 38, "reason": "Nearly won but..."}}
    ],
    "best_bet": {{
      "hypothesis": "...",
      "mechanism": "...",
      "why_survived": "..."
    }},
    "next_actions": {{
      "7_day": ["Action 1", "Action 2", "Action 3"],
      "30_day": ["Action 1", "Action 2", "Action 3"]
    }},
    "memory_patterns": ["Pattern 1", "Pattern 2"],
    "memory_strategies": ["Strategy 1"],
    "rejected_biases": ["Bias 1"]
  }}
}}
"""


def decide(
    ranked: list,
    all_hypotheses: list,
    exec_result: dict,
    problem: str,
    model: str,
) -> dict:
    """
    Issue the binding arbiter decision.

    Args:
        ranked: list from ranker (sorted by ev_score)
        all_hypotheses: full enriched list including research
        exec_result: dict from executor
        problem: original research problem
        model: Ollama model name

    Returns:
        arbiter_decision dict.
    """
    if not ranked:
        return _fallback_decision(all_hypotheses, problem)

    ranked_summary = _summarise_hypotheses(ranked)

    safe_exec = {
        "success": exec_result.get("success", False),
        "stdout": exec_result.get("stdout", "")[:600],
        "stderr": exec_result.get("stderr", "")[:300],
        "timed_out": exec_result.get("timed_out", False),
    } if exec_result else {"success": False, "stdout": "No experiment.", "stderr": ""}

    prompt = _PROMPT_TEMPLATE.format(
        problem=problem,
        ranked_summary=ranked_summary,
        exec_result=json.dumps(safe_exec, indent=2),
    )

    print("  [Arbiter] Calling LLM...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Arbiter] Empty LLM response - using fallback decision.", file=sys.stderr)
        return _fallback_decision(ranked, problem)

    parsed = _parse_json(raw)

    if isinstance(parsed, dict) and "arbiter_decision" in parsed:
        decision = parsed["arbiter_decision"]
        if isinstance(decision, dict) and "winner_id" in decision:
            winner_id = decision.get("winner_id")
            winner = next(
                (h for h in ranked if h.get("id") == winner_id),
                ranked[0] if ranked else {},
            )
            # Ensure best_bet fields are populated from the actual hypothesis
            # Strip accidental "Hyp:" prefix from LLM output
            bb = decision.get("best_bet", {})
            if bb.get("hypothesis", "").startswith("Hyp:"):
                bb["hypothesis"] = bb["hypothesis"][4:].strip()

            if not bb.get("hypothesis") and winner:
                decision["best_bet"] = {
                    "hypothesis": winner.get("hypothesis", ""),
                    "mechanism": winner.get("mechanism", ""),
                    "why_survived": decision.get("justification", "")[:200],
                }
            print(
                f"  [Arbiter] Winner: H{winner_id} "
                f"(final P={decision.get('final_p_correct','?')}%)"
            )
            return decision

    print("[Arbiter WARNING] Could not parse JSON - using fallback.", file=sys.stderr)
    return _fallback_decision(ranked, problem)


def _fallback_decision(hypotheses: list, problem: str) -> dict:
    """
    Build a minimal arbiter decision from the top-ranked hypothesis
    when LLM output cannot be parsed.
    """
    top = hypotheses[0] if hypotheses else {}
    return {
        "winner_id": top.get("id", 1),
        "final_p_correct": top.get("p_correct", 25),
        "justification": (
            "Fallback decision: selected the highest EV-scored hypothesis. "
            "Arbiter LLM call failed or returned unparseable output."
        ),
        "dissenting_views": [],
        "best_bet": {
            "hypothesis": top.get("hypothesis", "No hypothesis available."),
            "mechanism": top.get("mechanism", ""),
            "why_survived": "Highest p_correct after skeptic and research phases.",
        },
        "next_actions": {
            "7_day": [
                f"Run targeted literature review on: {top.get('hypothesis','')[:80]}",
                "Design and run a controlled experiment to test the kill condition",
                "Consult domain expert to validate the proposed mechanism",
            ],
            "30_day": [
                "Build a prototype or simulation based on the winning hypothesis",
                "Gather empirical data to update p_correct",
                "Publish or share preliminary findings for peer review",
            ],
        },
        "memory_patterns": [],
        "memory_strategies": [],
        "rejected_biases": [],
    }
