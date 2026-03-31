"""Claude Code CLI wrapper for conversational chat."""

from __future__ import annotations

import asyncio
import json
import logging

from app.core.config import settings

logger = logging.getLogger("arlo.assistant.llm")


class ClaudeError(Exception):
    pass


async def chat_with_claude(
    prompt: str,
    system_prompt: str | None = None,
    timeout: int | None = None,
) -> str:
    """Send a prompt to Claude Code CLI and return the text response.

    Uses --dangerously-skip-permissions for web search access.
    Returns the text response (not JSON).
    """
    if timeout is None:
        timeout = settings.claude_timeout_seconds

    cmd = [
        settings.claude_command, "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions",
    ]

    if settings.claude_model:
        cmd.extend(["--model", settings.claude_model])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    logger.info("Sending chat to Claude (timeout=%ds)", timeout)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        raise ClaudeError(f"Claude timed out after {timeout}s")

    stdout = stdout_bytes.decode("utf-8", errors="replace")

    if process.returncode != 0:
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        raise ClaudeError(f"Claude exited with code {process.returncode}: {stderr[:500]}")

    # Parse JSON output to extract the text response
    try:
        data = json.loads(stdout)
        return data.get("result", stdout)
    except json.JSONDecodeError:
        return stdout
