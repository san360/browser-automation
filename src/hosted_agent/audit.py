"""Tool-call audit middleware for the hosted agent.

Logs every tool invocation (name + arguments with secrets redacted) so `azd ai agent monitor` and Application
Insights show exactly what the agent did. It does not modify tool results or the response stream: rewriting the
stream (for example to inject the live-view link) can conflict with the Responses host's append-only projection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent_framework import function_middleware

logger = logging.getLogger("web_qa_agent")
_SENSITIVE = re.compile(r"(?i)(authorization|token|password|secret|liveviewurl)(['\"]?\s*[:=]\s*['\"]?)[^,'\"}\s]+")


def redact(text: str) -> str:
    return _SENSITIVE.sub(r"\1\2***", text)


@function_middleware
async def tool_audit(context: Any, call_next: Any) -> None:
    name = getattr(getattr(context, "function", None), "name", "") or ""
    logger.info("[tool] %s args=%s", name, redact(str(getattr(context, "arguments", "")))[:500])
    await call_next()
    result = str(getattr(context, "result", ""))
    if '"error"' in result[:400]:
        logger.warning("[tool] %s returned an error: %s", name, redact(result)[:400])
