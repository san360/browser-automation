"""Workaround: keep a hosted response alive when the agent stream carries a divergent text snapshot.

The Responses host projects agent text onto an append-only stream. When a "replace" text snapshot does not extend the
text already streamed, agent-framework-foundry-hosting (1.0.0b261015) raises "Cannot project a divergent replacement
text snapshot onto an append-only Responses stream" and the whole response fails, losing minutes of browser work. We
saw it on long browser runs right after Agent Framework stopped tool calls because of consecutive tool errors.

With this patch the replacement becomes the authoritative text (it is what `response.output_text.done` and the stored
response carry), no extra delta is emitted, and a warning with lengths only (no content) is logged. Streaming clients
may briefly show the superseded text. The patch applies only while the hosting package still raises this error.
"""

from __future__ import annotations

import inspect
import logging

logger = logging.getLogger("web_qa_agent.text_projection_fix")

_MARKER = "Cannot project a divergent replacement text snapshot"


def apply() -> bool:
    try:
        from agent_framework_foundry_hosting import _responses

        tracker = _responses._OutputItemTracker
        original = tracker._consume_text_update
        source = inspect.getsource(original)
    except (ImportError, AttributeError, OSError, TypeError):
        logger.info("Text projection patch not applied: hosting internals changed.")
        return False
    if getattr(original, "_divergence_fix", False) or _MARKER not in source:
        return False

    def _consume_text_update(self, text, merge_mode):
        try:
            return original(self, text, merge_mode)
        except RuntimeError as exc:
            if _MARKER not in str(exc):
                raise
            previous = "".join(self._accumulated)
            common = 0
            for a, b in zip(previous, text):
                if a != b:
                    break
                common += 1
            logger.warning(
                "Divergent replacement text snapshot (streamed %d chars, replacement %d chars, common prefix %d); "
                "keeping the replacement as the final text.", len(previous), len(text), common,
            )
            self._accumulated[:] = [text]
            return ""

    _consume_text_update._divergence_fix = True  # type: ignore[attr-defined]
    tracker._consume_text_update = _consume_text_update
    logger.info("Text projection patch applied: divergent text snapshots no longer fail the response.")
    return True
