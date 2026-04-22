"""
JSON-based persistent memory store.
Saves and loads all discovery runs across sessions.
"""
import json
import os
import re
from datetime import datetime

import config


def filename_for_problem(problem: str) -> str:
    """
    Generate a stable, human-readable filename from a problem string.
    Example: "Does caffeine affect sleep?" -> "memory_does_caffeine_affect_sleep.json"
    """
    slug = re.sub(r"[^a-z0-9]+", "_", problem.lower().strip())
    slug = slug.strip("_")[:50]
    return f"memory_{slug}.json"

_SKELETON = {
    "runs": [],
    "patterns": [],
    "rejected_biases": [],
    "high_yield_domains": [],
    "successful_strategies": [],
}


def load_memory() -> dict:
    """Load memory.json, or return a fresh skeleton if it doesn't exist."""
    if not os.path.exists(config.MEMORY_FILE):
        return {k: list(v) for k, v in _SKELETON.items()}
    try:
        with open(config.MEMORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys exist even if file is from an older version
        for k, v in _SKELETON.items():
            data.setdefault(k, list(v))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[MEMORY WARNING] Could not load {config.MEMORY_FILE}: {exc}")
        print("[MEMORY] Starting with empty memory.")
        return {k: list(v) for k, v in _SKELETON.items()}


def save_memory(memory: dict) -> None:
    """Persist memory dict to memory.json with pretty-printing."""
    try:
        with open(config.MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, default=str, ensure_ascii=False)
    except OSError as exc:
        print(f"[MEMORY ERROR] Could not save memory: {exc}")


def add_run(memory: dict, run_data: dict) -> dict:
    """
    Append a run record to memory["runs"].
    Rotates out oldest entries beyond MAX_MEMORY_RUNS.
    """
    run_data["timestamp"] = datetime.now().isoformat()
    memory["runs"].append(run_data)

    if len(memory["runs"]) > config.MAX_MEMORY_RUNS:
        memory["runs"] = memory["runs"][-config.MAX_MEMORY_RUNS :]

    return memory


def format_memory_context(memory: dict) -> str:
    """
    Build a compact string summarising previous runs for LLM prompt injection.
    Uses at most the 2 most recent runs plus global patterns/strategies.
    """
    lines = []

    recent = memory.get("runs", [])[-2:]
    if recent:
        lines.append("=== PREVIOUS RUNS (most recent first) ===")
        for run in reversed(recent):
            ts = run.get("timestamp", "unknown")[:10]
            prob = run.get("problem", "unknown problem")
            decision = run.get("arbiter_decision", {})
            best = decision.get("best_bet", {}).get("hypothesis", "N/A")
            p = decision.get("final_p_correct", "?")
            lines.append(
                f"[{ts}] Problem: {prob}\n"
                f"  Best bet: {best} (P={p}%)"
            )

    patterns = memory.get("patterns", [])
    if patterns:
        lines.append("\n=== DETECTED PATTERNS ===")
        for p in patterns[-5:]:
            lines.append(f"  • {p}")

    rejected = memory.get("rejected_biases", [])
    if rejected:
        lines.append("\n=== REJECTED BIASES (avoid these) ===")
        for r in rejected[-5:]:
            lines.append(f"  ✗ {r}")

    strategies = memory.get("successful_strategies", [])
    if strategies:
        lines.append("\n=== SUCCESSFUL STRATEGIES ===")
        for s in strategies[-5:]:
            lines.append(f"  ✓ {s}")

    if not lines:
        return "No prior memory - this is the first run."

    return "\n".join(lines)


def merge_arbiter_memory(memory: dict, arbiter_decision: dict) -> dict:
    """
    Extract memory update fields from the arbiter's decision and merge
    them into the global memory lists, deduplicating.
    """
    def _extend_unique(lst: list, new_items) -> list:
        if not isinstance(new_items, list):
            return lst
        seen = set(lst)
        for item in new_items:
            if isinstance(item, str) and item and item not in seen:
                lst.append(item)
                seen.add(item)
        return lst

    memory["patterns"] = _extend_unique(
        memory.get("patterns", []),
        arbiter_decision.get("memory_patterns", []),
    )
    memory["successful_strategies"] = _extend_unique(
        memory.get("successful_strategies", []),
        arbiter_decision.get("memory_strategies", []),
    )
    memory["rejected_biases"] = _extend_unique(
        memory.get("rejected_biases", []),
        arbiter_decision.get("rejected_biases", []),
    )

    # Rotate long lists
    for key in ("patterns", "successful_strategies", "rejected_biases"):
        if len(memory[key]) > 50:
            memory[key] = memory[key][-50:]

    return memory
