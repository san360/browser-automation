"""Workaround: correct the token usage that the hosted agent reports in its Responses output.

agent-framework-core (1.22.0) streams tool-loop usage as cumulative snapshots (usage Content with
merge_mode="replace"), but agent-framework-foundry-hosting (1.0.0b261015) adds every snapshot to its running total.
On a 24-model-call browser run the hosted agent reported 1,804,793 input tokens, while Azure Monitor and the
agent's own OpenTelemetry spans recorded 174,538. Only the reported number is wrong; billing follows real usage.

The patch makes the response usage honour "replace" snapshots. It applies only while the hosting package still
contains the additive code path, so it switches itself off once the package is fixed.
"""

from __future__ import annotations

import inspect
import logging

logger = logging.getLogger("web_qa_agent.usage_fix")

_ADDITIVE_LINE = "self._usage_details = add_usage_details(self._usage_details, content.usage_details)"


def apply() -> bool:
    try:
        from agent_framework_foundry_hosting import _responses

        tracker = _responses._OutputItemTracker
        original = tracker.handle
        source = inspect.getsource(original)
    except (ImportError, AttributeError, OSError, TypeError):
        logger.info("Usage accounting patch not applied: hosting internals changed.")
        return False
    if getattr(original, "_usage_fix", False) or _ADDITIVE_LINE not in source:
        return False

    async def handle(self, content, message_id=None, *, approval_storage=None):
        if content.type == "usage" and getattr(content, "merge_mode", None) == "replace":
            self._usage_details = dict(content.usage_details or {})
            return
        async for event in original(self, content, message_id, approval_storage=approval_storage):
            yield event

    handle._usage_fix = True  # type: ignore[attr-defined]
    tracker.handle = handle
    logger.info("Usage accounting patch applied: cumulative usage snapshots replace the total instead of adding.")
    return True
