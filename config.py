"""
ADM-3 Configuration
All tuneable parameters live here. Override per-run with CLI flags.
"""
import argparse
import sys

# ── LLM ──────────────────────────────────────────────────────────────────────
MODEL = "qwen2.5:14b"
OLLAMA_URL = "http://localhost:11434/api/generate"
LLM_TIMEOUT = 180  # seconds per LLM call

# ── Loop ──────────────────────────────────────────────────────────────────────
ITERATIONS = 3

# ── Code execution ────────────────────────────────────────────────────────────
EXEC_TIMEOUT = 30  # seconds

# ── Search ────────────────────────────────────────────────────────────────────
SEARCH_RESULTS = 5  # results per DuckDuckGo query

# ── Memory ────────────────────────────────────────────────────────────────────
MEMORY_FILE = "memory.json"  # overridden at runtime by store.filename_for_problem()
MAX_MEMORY_RUNS = 20  # oldest runs are rotated out beyond this


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ADM-3 - Autonomous Discovery Multi-Agent Framework"
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=ITERATIONS,
        help=f"Number of discovery iterations (default: {ITERATIONS})",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=MODEL,
        help=f"Ollama model to use (default: {MODEL})",
    )
    parser.add_argument(
        "--problem", "-p",
        type=str,
        default=None,
        help="Research problem (skips interactive prompt)",
    )
    return parser.parse_args()
