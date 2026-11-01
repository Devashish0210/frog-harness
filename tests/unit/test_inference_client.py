"""Unit tests for InferenceClient hybrid protocol."""

import json
from unittest.mock import MagicMock, patch
import pytest
from frognano_harness.inference_client import InferenceClient, ModelResponse


def test_parse_native_tool_calls() -> None:
    client = InferenceClient("http://127.0.0.1:8080/v1")
    raw_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "I will read the file.",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "src/main.py"}),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 150, "completion_tokens": 40},
    }

    resp = client.parse_completion_response(raw_response)
    assert resp.content == "I will read the file."
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["name"] == "read_file"
    assert resp.tool_calls[0]["arguments"] == {"path": "src/main.py"}
    assert resp.prompt_tokens == 150
    assert resp.completion_tokens == 40


def test_parse_markdown_action_code_fences_fallback() -> None:
    client = InferenceClient("http://127.0.0.1:8080/v1")
    raw_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "I am writing the file.\n\n"
                        "```action\n"
                        '{"tool": "write_file", "arguments": {"path": "test.txt", "content": "hi"}}\n'
                        "```\n"
                    ),
                }
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }

    resp = client.parse_completion_response(raw_response)
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["name"] == "write_file"
    assert resp.tool_calls[0]["arguments"] == {"path": "test.txt", "content": "hi"}
