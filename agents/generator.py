"""
ADM-3 Step 1 - Generator Agent.
Produces 10-20 diverse hypotheses with calibrated P(correct) scores.
"""
import json
import re
import sys

from tools.llm import query_llm


# ── JSON parsing helper (shared pattern across all agents) ───────────────────

def _parse_json(text: str) -> dict | list | None:
    """
    Try to extract a JSON object or array from LLM output.
    1. Direct json.loads
    2. First {...} / [...] block via regex
    3. Return None on failure
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try array
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


_PROMPT_TEMPLATE = """\
You are the GENERATOR AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).

RESEARCH PROBLEM:
{problem}

PRIOR MEMORY CONTEXT:
{memory_context}

YOUR TASK:
Generate 10-15 diverse, high-variance hypotheses to address the research problem.
Use these strategies: first principles, inversion, extreme scaling, constraint removal, cross-domain analogies.

For each hypothesis produce:
- id: integer starting at 1
- hypothesis: clear, concise statement (1-2 sentences)
- mechanism: the underlying mechanism or causal pathway
- expected_effect: direction and magnitude of the expected effect
- p_correct: your calibrated probability of being correct (integer 0-100)
- justification: one sentence explaining your p_correct estimate

Aim for HIGH DIVERSITY - cover different mechanisms, scales, and domains.
Avoid repeating previously rejected biases from memory.

CRITICAL: Output ONLY valid JSON. No markdown, no explanation outside the JSON.
Use exactly this structure:
{{
  "hypotheses": [
    {{
      "id": 1,
      "hypothesis": "...",
      "mechanism": "...",
      "expected_effect": "...",
      "p_correct": 40,
      "justification": "..."
    }}
  ]
}}
"""


def generate(problem: str, memory_context: str, model: str) -> list:
    """
    Generate hypotheses for the given problem.

    Returns:
        list of hypothesis dicts. Falls back to a single raw-text entry
        if JSON parsing fails.
    """
    prompt = _PROMPT_TEMPLATE.format(
        problem=problem,
        memory_context=memory_context or "No prior memory.",
    )

    print("  [Generator] Calling LLM...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Generator] Empty LLM response.", file=sys.stderr)
        return []

    parsed = _parse_json(raw)

    if isinstance(parsed, dict) and "hypotheses" in parsed:
        hypotheses = parsed["hypotheses"]
        if isinstance(hypotheses, list) and hypotheses:
            # Ensure required fields exist with defaults
            cleaned = []
            for i, h in enumerate(hypotheses):
                cleaned.append({
                    "id": h.get("id", i + 1),
                    "hypothesis": h.get("hypothesis", ""),
                    "mechanism": h.get("mechanism", ""),
                    "expected_effect": h.get("expected_effect", ""),
                    "p_correct": int(h.get("p_correct", 30)),
                    "justification": h.get("justification", ""),
                })
            print(f"  [Generator] {len(cleaned)} hypotheses generated.")
            return cleaned

    # Fallback: return raw text wrapped in a single entry
    print("[Generator WARNING] Could not parse JSON - using raw text fallback.", file=sys.stderr)
    return [{
        "id": 1,
        "hypothesis": raw[:500],
        "mechanism": "Unstructured LLM response",
        "expected_effect": "Unknown",
        "p_correct": 25,
        "justification": "Fallback due to JSON parse failure",
    }]
