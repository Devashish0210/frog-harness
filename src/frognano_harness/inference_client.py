"""Local llama.cpp OpenAI-compatible inference client."""

from dataclasses import dataclass, field
import json
import re
from typing import Any, Optional
import urllib.error
import urllib.request

from frognano_harness.exceptions import HarnessError

ACTION_BLOCK_REGEX = re.compile(
    r"```(?:action|json)\s*\n([\s\S]*?)\n```", re.IGNORECASE
)


@dataclass(frozen=True)
class ModelResponse:
    """Structured response from the local model."""
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class InferenceClient:
    """Communicates with local llama.cpp OpenAI-compatible endpoint."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8080/v1",
        model_alias: str = "frognano",
        timeout_sec: int = 180,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_alias = model_alias
        self.timeout_sec = timeout_sec

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> ModelResponse:
        """Send chat completion request to local inference endpoint."""
        url = f"{self.endpoint}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model_alias,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]
            payload["tool_choice"] = "auto"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw_body = resp.read().decode("utf-8")
                raw_json = json.loads(raw_body)
                return self.parse_completion_response(raw_json)
        except urllib.error.URLError as e:
            raise HarnessError(f"Inference server connection failed at {url}: {e}") from e
        except json.JSONDecodeError as e:
            raise HarnessError(f"Invalid JSON returned from inference server: {e}") from e

    def parse_completion_response(self, raw: dict[str, Any]) -> ModelResponse:
        """Parse native OpenAI tool_calls or fallback to markdown action code fences."""
        choices = raw.get("choices", [])
        if not choices:
            raise HarnessError("Empty choices returned from model completion.")

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        tool_calls: list[dict[str, Any]] = []

        # 1. Primary: Native OpenAI function calling
        native_calls = message.get("tool_calls", [])
        if native_calls and isinstance(native_calls, list):
            for tc in native_calls:
                func = tc.get("function", {})
                name = func.get("name")
                raw_args = func.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        parsed_args = {"_raw": raw_args}
                else:
                    parsed_args = raw_args or {}

                if name:
                    tool_calls.append({"name": name, "arguments": parsed_args})

        # 2. Fallback: Parse markdown ```action or ```json blocks if no native tool calls
        if not tool_calls and content:
            for match in ACTION_BLOCK_REGEX.finditer(content):
                block_str = match.group(1).strip()
                try:
                    parsed = json.loads(block_str)
                    if isinstance(parsed, dict):
                        if "tool" in parsed:
                            tool_calls.append({
                                "name": parsed["tool"],
                                "arguments": parsed.get("arguments", {})
                            })
                        elif "name" in parsed:
                            tool_calls.append({
                                "name": parsed["name"],
                                "arguments": parsed.get("arguments", {})
                            })
                except json.JSONDecodeError:
                    continue

        usage = raw.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
