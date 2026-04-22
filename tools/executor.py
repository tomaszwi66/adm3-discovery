"""
Sandboxed Python code executor.
Writes generated code to a temp file and runs it in a subprocess with a timeout.
Strips dangerous builtins before execution.
"""
import os
import re
import subprocess
import sys
import tempfile

import config

# Patterns to strip from generated code before execution.
# We block direct shell escape and network calls.
_DANGEROUS_PATTERNS = [
    r"\bos\.system\s*\(",
    r"\bsubprocess\b",
    r"\b__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bopen\s*\(.*[\"'][wa][\"']",   # file writes
    r"\burllib\.request\b",
    r"\brequests\b",
    r"\bsocket\b",
]
_DANGER_RE = re.compile("|".join(_DANGEROUS_PATTERNS))


def _sanitize(code: str) -> tuple[str, list]:
    """
    Scan code for dangerous patterns.
    Returns (sanitized_code, list_of_warnings).
    Lines containing dangerous patterns are commented out.
    """
    warnings = []
    clean_lines = []
    for lineno, line in enumerate(code.splitlines(), 1):
        if _DANGER_RE.search(line):
            warnings.append(f"  Line {lineno} blocked (dangerous pattern): {line.strip()}")
            clean_lines.append(f"# [BLOCKED] {line}")
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines), warnings


def execute_code(code: str, timeout: int = None) -> dict:
    """
    Execute a Python code string in a sandboxed subprocess.

    Returns:
        {
            "success": bool,
            "stdout": str,      # capped at 5000 chars
            "stderr": str,      # capped at 2000 chars
            "returncode": int,
            "warnings": list,   # sanitization warnings
            "timed_out": bool,
        }
    """
    timeout = timeout or config.EXEC_TIMEOUT

    if not code or not code.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "No code provided.",
            "returncode": -1,
            "warnings": [],
            "timed_out": False,
        }

    sanitized, warnings = _sanitize(code)
    if warnings:
        print("[EXECUTOR] Dangerous patterns blocked in generated code:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(sanitized)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "warnings": warnings,
            "timed_out": False,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s.",
            "returncode": -1,
            "warnings": warnings,
            "timed_out": True,
        }

    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Python interpreter not found.",
            "returncode": -1,
            "warnings": warnings,
            "timed_out": False,
        }

    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "warnings": warnings,
            "timed_out": False,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
