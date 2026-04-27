"""OpenClaw model execution boundary for external-learning.

This module delegates model calls to OpenClaw's configured model registry and auth
store. It accepts model aliases such as Minimax and GPT54, then invokes the Node
runtime shim that uses OpenClaw's own simple-completion path. No API keys, provider
URLs, or OpenAI-compatible settings are owned by this skill.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class ModelExecutionUnavailable(RuntimeError):
    pass


def _executor_script() -> Path:
    return Path(__file__).with_name("openclaw_model_executor.mjs")


def _execute_with_openclaw(prompt: str, model: str) -> dict[str, Any]:
    script = _executor_script()
    if not script.exists():
        raise ModelExecutionUnavailable(f"OpenClaw model executor script is missing: {script}")

    payload = json.dumps({"prompt": prompt, "model": model}, ensure_ascii=False)
    try:
        completed = subprocess.run(
            ["node", str(script)],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ModelExecutionUnavailable(f"OpenClaw model execution failed: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ModelExecutionUnavailable(f"OpenClaw model execution failed: {detail}")
    return _ensure_dict(completed.stdout)


def _ensure_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError as exc:
            raise ModelExecutionUnavailable(f"model executor returned non-JSON text: {exc}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ModelExecutionUnavailable(f"model executor returned unsupported type: {type(result).__name__}")


def _run(prompt: str, model: str) -> dict[str, Any]:
    return _execute_with_openclaw(prompt=prompt, model=model)


def run_screen_judgment(prompt: str, model: str = "Minimax") -> dict[str, Any]:
    return _run(prompt, model)


def run_final_judgment(prompt: str, model: str = "GPT54") -> dict[str, Any]:
    return _run(prompt, model)
