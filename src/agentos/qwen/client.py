"""Qwen Cloud API client for AgentOS."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Literal, Optional
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agentos.core.config import get_config, QwenConfig

logger = logging.getLogger(__name__)


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
    )
    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[ChatCompletionToolParam]] = None,
        tool_choice: Optional[Literal["auto", "none", "required"]] = "auto",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> ChatResponse | AsyncGenerator[str, None]:
        """Chat completion with optional function calling."""
        if stream:
            return self._chat_stream(messages, tools, tool_choice, temperature, max_tokens)

        response = await self.client.chat.completions.create(
            model=self.config.model,
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