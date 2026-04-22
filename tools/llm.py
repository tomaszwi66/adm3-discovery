"""
Ollama LLM interface.
Communicates with the local Ollama REST API at http://localhost:11434.
"""
import json
import sys
import requests

import config


def query_llm(prompt: str, model: str = None, timeout: int = None, json_mode: bool = False) -> str:
    """
    Send a prompt to Ollama and return the response text.

    Raises SystemExit with a clear message if Ollama is not reachable.
    Returns empty string on any other error (logged to stderr).
    """
    model = model or config.MODEL
    timeout = timeout or config.LLM_TIMEOUT

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(config.OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    except requests.exceptions.ConnectionError:
        print(
            "\n[LLM ERROR] Cannot connect to Ollama at "
            f"{config.OLLAMA_URL}\n"
            "Make sure Ollama is running: ollama serve\n"
            f"And that the model is pulled: ollama pull {model}",
            file=sys.stderr,
        )
        sys.exit(1)

    except requests.exceptions.Timeout:
        print(
            f"\n[LLM ERROR] Request timed out after {timeout}s. "
            "Consider increasing LLM_TIMEOUT in config.py.",
            file=sys.stderr,
        )
        return ""

    except requests.exceptions.HTTPError as exc:
        print(f"\n[LLM ERROR] HTTP error from Ollama: {exc}", file=sys.stderr)
        return ""

    except (KeyError, json.JSONDecodeError) as exc:
        print(f"\n[LLM ERROR] Unexpected response format: {exc}", file=sys.stderr)
        return ""
