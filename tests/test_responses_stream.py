"""Browser-session correlation from streamed tool calls and outputs."""

import json
from types import SimpleNamespace as NS

import pytest

from demo_common.reporting import RunRecorder
from demo_common.responses_stream import consume_stream
from demo_common.scenarios import find_scenario, render


@pytest.mark.parametrize("item_type", ["remote_function_call_output", "function_call_output", "mcp_call_output",
                                       "mcp_call"])
def test_session_creation_outputs_are_captured(tmp_path, item_type):
    recorder = RunRecorder(render(find_scenario("02")), "prompt", "gpt-4.1-mini", quiet=True, runs_dir=tmp_path)
    item = NS(type=item_type, name="create_browser_session", output=json.dumps({
        "content": [{"type": "text", "text": '{"browserSessionId": "created-browser"}'}],
    }))
    consume_stream([NS(type="response.output_item.done", item=item)], recorder)
    assert recorder.browser_session_ids == ["created-browser"]


def test_session_arguments_are_captured_when_creation_output_is_not_exposed(tmp_path):
    recorder = RunRecorder(render(find_scenario("02")), "hosted", "gpt-4.1-mini", quiet=True, runs_dir=tmp_path)
    item = NS(type="remote_function_call", name="browser_navigate", call_id="call-1",
              arguments='{"browserSessionId": "browser-1", "url": "https://example.com"}')
    consume_stream([NS(type="response.output_item.done", item=item)], recorder)
    assert recorder.browser_session_ids == ["browser-1"]
    assert recorder.actions[0]["call_id"] == "call-1"
    assert recorder.actions[0]["arguments"]["browserSessionId"] == "browser-1"
