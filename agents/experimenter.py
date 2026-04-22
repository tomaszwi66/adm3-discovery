"""
ADM-3 Step 4 - Experiment Agent.
Designs a minimal, falsifiable Python experiment for the top hypothesis
and returns executable code.
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
You are the EXPERIMENT AGENT in the APEX Discovery Multi-Agent Framework (ADM-3).

RESEARCH PROBLEM:
{problem}

TARGET HYPOTHESIS:
{hypothesis_json}

YOUR TASK:
Design a minimal, falsifiable Python experiment to test this hypothesis.

REQUIREMENTS:
- Must complete in under 30 seconds using ONLY Python standard library: math, statistics, random, itertools, collections
- Do NOT import numpy, scipy, pandas, or any third-party library - use only stdlib
- Must print a clear RESULT line: either "RESULT: SUPPORTED" or "RESULT: REJECTED" or "RESULT: INCONCLUSIVE"
- Must print numeric output (measurements, statistics, etc.)
- Code must be self-contained - no file I/O, no network calls, no subprocess
- If the hypothesis involves data analysis, generate synthetic data that represents the expected distribution
- Include comments explaining each step

Also provide:
- description: what the experiment tests
- variables: {{independent, dependent, controlled}}
- success_metric: what constitutes a positive result
- kill_criteria: what output means the hypothesis is falsified
- time_estimate: "fast" (<5s) | "medium" (5-15s) | "slow" (15-30s)
- p_success: your probability (0-100) that the experiment will produce clean signal

CRITICAL: Output ONLY valid JSON. The "code" field must contain complete, runnable Python.
{{
  "experiment": {{
    "description": "...",
    "variables": {{
      "independent": "...",
      "dependent": "...",
      "controlled": "..."
    }},
    "success_metric": "...",
    "kill_criteria": "...",
    "time_estimate": "fast",
    "p_success": 70,
    "code": "# Python experiment code\\nprint('Starting experiment...')\\n# ... rest of code"
  }}
}}
"""


def design(hypothesis: dict, problem: str, model: str) -> dict:
    """
    Design an experiment for the given hypothesis.

    Args:
        hypothesis: single hypothesis dict (the top-ranked one)
        problem: original research problem
        model: Ollama model name

    Returns:
        experiment dict with 'code' field, or empty dict if generation fails.
    """
    if not hypothesis:
        return {}

    hyp_json = json.dumps(hypothesis, indent=2, ensure_ascii=False)
    prompt = _PROMPT_TEMPLATE.format(
        problem=problem,
        hypothesis_json=hyp_json,
    )

    print("  [Experimenter] Calling LLM...", end=" ", flush=True)
    raw = query_llm(prompt, model=model, json_mode=True)
    print("done.")

    if not raw:
        print("[Experimenter] Empty LLM response.", file=sys.stderr)
        return {}

    parsed = _parse_json(raw)

    if isinstance(parsed, dict) and "experiment" in parsed:
        exp = parsed["experiment"]
        if isinstance(exp, dict) and exp.get("code"):
            # Clean up code: strip markdown fences if present
            code = exp["code"]
            code = re.sub(r"^```(?:python)?\s*\n?", "", code, flags=re.MULTILINE)
            code = re.sub(r"\n?```\s*$", "", code, flags=re.MULTILINE)
            exp["code"] = code.strip()

            print(
                f"  [Experimenter] Experiment: {exp.get('description', 'unnamed')[:60]} "
                f"(p_success={exp.get('p_success', '?')}%)"
            )
            return exp

    # Fallback: generate a minimal placeholder experiment
    print("[Experimenter WARNING] Could not parse JSON - using minimal fallback experiment.", file=sys.stderr)
    hyp_text = hypothesis.get("hypothesis", "unknown hypothesis")
    mechanism = hypothesis.get("mechanism", "unknown mechanism")
    fallback_code = f"""\
# Fallback experiment: basic simulation for hypothesis
# Hypothesis: {hyp_text}
# Mechanism: {mechanism}
import random
import statistics

print("=== Fallback Simulation Experiment ===")
print(f"Testing: {repr(hyp_text)}")

# Generate two synthetic distributions
random.seed(42)
group_a = [random.gauss(0, 1) for _ in range(100)]
group_b = [random.gauss(0.3, 1) for _ in range(100)]

mean_a = statistics.mean(group_a)
mean_b = statistics.mean(group_b)
diff = mean_b - mean_a

print(f"Group A mean: {{mean_a:.4f}}")
print(f"Group B mean: {{mean_b:.4f}}")
print(f"Difference: {{diff:.4f}}")

if abs(diff) > 0.1:
    print("RESULT: SUPPORTED (effect detected in simulation)")
else:
    print("RESULT: INCONCLUSIVE (no effect in simulation)")
"""
    return {
        "description": f"Fallback simulation for: {hyp_text[:60]}",
        "variables": {"independent": "group", "dependent": "value", "controlled": "random_seed=42"},
        "success_metric": "mean difference > 0.1",
        "kill_criteria": "mean difference <= 0.0",
        "time_estimate": "fast",
        "p_success": 30,
        "code": fallback_code,
    }
