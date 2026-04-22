"""
ADM-3 Step 2 - Skeptic Agent.
Aggressively falsifies every hypothesis.
Classifies each as Survives / Weak / Rejected and drops Rejected ones.
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
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


_PROMPT_TEMPLATE = """\
You are the SKEPTIC AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).

RESEARCH PROBLEM:
{problem}

HYPOTHESES TO FALSIFY:
{hypotheses_json}

YOUR TASK:
Aggressively attempt to falsify every hypothesis. For each:
1. List concrete failure_modes (physical/logical/statistical flaws)
2. Identify hidden_assumptions that may be false
3. Cite any known counterexamples or prior failures
4. Assign failure_probability (0-100): how likely is this hypothesis WRONG?
5. Compute updated_p_correct = original p_correct adjusted down by your analysis (0-100)
6. Classify:
   - "Survives"  → updated_p_correct >= 40
   - "Weak"      → updated_p_correct 15-39
   - "Rejected"  → updated_p_correct < 15
7. Define kill_condition: a single falsifiable test that would definitively disprove this

Be ruthless. A hypothesis that cannot be quickly tested or has obvious logical gaps should be classified Weak or Rejected.

CRITICAL: Output ONLY valid JSON. No markdown, no prose outside the JSON.
{{
  "analyzed": [
    {{
      "id": 1,
      "failure_modes": ["..."],
      "hidden_assumptions": ["..."],
      "counterexamples": ["..."],
      "failure_probability": 60,
      "updated_p_correct": 30,
      "classification": "Weak",
      "kill_condition": "..."
    }}
  ]
}}
"""


def analyze(hypotheses: list, problem: str, model: str) -> list:
    """
    Falsify each hypothesis and return a filtered list.
    Drops 'Rejected' hypotheses. Merges skeptic fields into hypothesis dicts.

    Returns:
        list of enriched hypothesis dicts (Survives + Weak only).
    """
    if not hypotheses:
        return []

    hyp_json = json.dumps(hypotheses, indent=2, ensure_ascii=False)
    prompt = _PROMPT_TEMPLATE.format(
        problem=problem,
        hypotheses_json=hyp_json,
    )

    print("  [Skeptic] Calling LLM...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Skeptic] Empty LLM response - passing all hypotheses through.", file=sys.stderr)
        return hypotheses

    parsed = _parse_json(raw)

    # Build a lookup by id
    hyp_by_id = {h["id"]: h for h in hypotheses}

    if isinstance(parsed, dict) and "analyzed" in parsed:
        analyzed = parsed["analyzed"]
        if isinstance(analyzed, list):
            merged = []
            for a in analyzed:
                hid = a.get("id")
                original = hyp_by_id.get(hid, {})
                classification = a.get("classification", "Weak")
                updated_p = int(a.get("updated_p_correct", original.get("p_correct", 25)))

                # Reclassify based on updated_p_correct using corrected thresholds
                if updated_p >= 25:
                    classification = "Survives"
                elif updated_p >= 12:
                    classification = "Weak"
                else:
                    classification = "Rejected"

                if classification == "Rejected":
                    continue  # Drop rejected hypotheses

                merged_hyp = {**original, **{
                    "failure_modes": a.get("failure_modes", []),
                    "hidden_assumptions": a.get("hidden_assumptions", []),
                    "counterexamples": a.get("counterexamples", []),
                    "failure_probability": a.get("failure_probability", 50),
                    "updated_p_correct": a.get("updated_p_correct", original.get("p_correct", 25)),
                    "classification": classification,
                    "kill_condition": a.get("kill_condition", ""),
                }}
                # Overwrite p_correct with skeptic's updated value
                merged_hyp["p_correct"] = merged_hyp["updated_p_correct"]
                merged.append(merged_hyp)

            survived = [h for h in merged if h["classification"] == "Survives"]
            weak = [h for h in merged if h["classification"] == "Weak"]
            print(
                f"  [Skeptic] {len(survived)} Survive, "
                f"{len(weak)} Weak, "
                f"{len(hypotheses) - len(survived) - len(weak)} Rejected."
            )
            return survived + weak

    # Fallback: return all hypotheses with a default Weak classification
    print("[Skeptic WARNING] Could not parse JSON - returning all as Weak.", file=sys.stderr)
    for h in hypotheses:
        h.setdefault("classification", "Weak")
        h.setdefault("kill_condition", "")
        h.setdefault("failure_modes", [])
    return hypotheses
