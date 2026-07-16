"""Qwen Cloud API client for Aki."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Literal, Optional, cast

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agentos.core.config import get_config, QwenConfig

logger = logging.getLogger(__name__)

# Known Qwen model identifiers used by this project (pulled from config.yaml's
# qwen.model / qwen.extraction_model / qwen.consolidation_model and the
# QwenConfig default in core/config.py). This is not an exhaustive list of
# every model DashScope offers — just the variants this codebase has actually
# been configured/tested with. The Cockpit model selector lets users pick one
# of these or type a custom string, since QwenClient.chat() accepts any
# `model` override without validation.
KNOWN_QWEN_MODELS: list[str] = [
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen-max",
]


def _before_sleep_callback(retry_state):
    """Notify connection attempts to the UI status callback if present."""
    status_callback = retry_state.kwargs.get("status_callback")
    attempt = retry_state.attempt_number
    exc = retry_state.outcome.exception()

    msg = f"⚠️ Conexión lenta. Reintentando llamada a Qwen (intento {attempt + 1})..."
    if exc:
        msg = f"⚡ Error de red ({type(exc).__name__}). Reintentando llamada a Qwen (intento {attempt + 1})..."

    if status_callback:
        status_callback(msg)
    else:
        logger.warning(msg)


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, int]
    model: str
    finish_reason: str


@dataclass
class EmbeddingResponse:
    embeddings: list[list[float]]
    usage: dict[str, int]


class QwenStructuredJSONError(RuntimeError):
    """Raised when Qwen cannot return usable structured JSON."""


class QwenClient:
    """Async client for Qwen Cloud API (OpenAI-compatible)."""

    def __init__(self, config: Optional[QwenConfig] = None):
        self.config = config or get_config().qwen
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=_before_sleep_callback,
    )
    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]] = None,
        tool_choice: Optional[Literal["auto", "none", "required"]] = "auto",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        model: str | None = None,
        status_callback: Optional[Callable[[str], None]] = None,
        token_callback: Optional[Callable[[str], None]] = None,
    ) -> ChatResponse | AsyncGenerator[str, None]:
        """Chat completion with optional function calling."""
        if stream:
            return self._chat_stream(messages, tools, tool_choice, temperature, max_tokens)

        if token_callback is not None:
            api_stream = await self.client.chat.completions.create(
                model=model or self.config.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            accumulated_content = []
            tool_calls_map = {}
            finish_reason = "stop"
            response_model = model or self.config.model

            async for chunk in api_stream:
                if chunk.model:
                    response_model = chunk.model
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    accumulated_content.append(delta.content)
                    token_callback(delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc.id or "",
                                "type": tc.type or "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc.id:
                            tool_calls_map[idx]["id"] = tc.id
                        if tc.type:
                            tool_calls_map[idx]["type"] = tc.type
                        if tc.function:
                            if tc.function.name:
                                tool_calls_map[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_map[idx]["function"]["arguments"] += tc.function.arguments

            tool_calls = []
            for idx in sorted(tool_calls_map.keys()):
                tc_data = tool_calls_map[idx]
                args_str = tc_data["function"]["arguments"]
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = args_str
                tool_calls.append({
                    "id": tc_data["id"],
                    "type": tc_data["type"],
                    "function": {
                        "name": tc_data["function"]["name"],
                        "arguments": args,
                    }
                })

            return ChatResponse(
                content="".join(accumulated_content),
                tool_calls=tool_calls,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                model=response_model,
                finish_reason=finish_reason,
            )

        response = await self.client.chat.completions.create(
            model=model or self.config.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            tool_calls=[
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    },
                }
                for tc in (choice.message.tool_calls or [])
            ],
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
        )

    async def structured_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: Optional[int] = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Request a JSON object from Qwen and parse it strictly."""
        json_system_prompt = system_prompt or (
            "You are a structured extraction assistant. Return only valid JSON. "
            "Do not wrap the response in Markdown fences or add commentary."
        )
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": json_system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.chat(
                messages,
                tool_choice="none",
                temperature=0.0,
                max_tokens=max_tokens,
                model=model,
            )
        except Exception as exc:  # external API failures are recoverable by callers
            raise QwenStructuredJSONError(f"Qwen request failed: {exc}") from exc

        content = cast(ChatResponse, response).content.strip()
        try:
            parsed = json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise QwenStructuredJSONError("Qwen response was not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise QwenStructuredJSONError("Qwen response must be a JSON object")
        return parsed

    async def _chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]],
        tool_choice: Optional[Literal["auto", "none", "required"]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion."""
        stream = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        before_sleep=_before_sleep_callback,
    )
    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        """Generate embeddings for texts."""
        response = await self.client.embeddings.create(
            model=self.config.embedding_model,
            input=texts,
        )

        return EmbeddingResponse(
            embeddings=[d.embedding for d in response.data],
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        )

    async def embed_one(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        resp = await self.embed([text])
        return resp.embeddings[0]

    def build_tools_schema(self, skills: list) -> list[ChatCompletionToolParam]:
        """Convert skills to OpenAI function calling format."""
        tools = []
        for skill in skills:
            for fn_name in skill.functions:
                # Get function schema from skill
                fn_schema = skill.get_function_schema(fn_name)
                if fn_schema:
                    tools.append(ChatCompletionToolParam(
                        type="function",
                        function=fn_schema,
                    ))
        return tools


def _strip_json_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).removeprefix("json").strip()
    return content


# Global client instance
_client: Optional[QwenClient] = None


def get_qwen_client() -> QwenClient:
    global _client
    if _client is None:
        _client = QwenClient()
    return _client


async def close_qwen_client() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None
