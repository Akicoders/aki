import pytest

from agentos.qwen.client import ChatResponse, QwenClient, QwenStructuredJSONError


class FakeQwenClient(QwenClient):
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.messages = None

    async def chat(self, messages, **kwargs):
        self.messages = messages
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_structured_json_returns_parsed_response():
    client = FakeQwenClient(
        ChatResponse(
            content='{"facts": [{"title": "Runtime", "content": "Uses uv"}]}',
            tool_calls=[],
            usage={},
            model="fake-qwen",
            finish_reason="stop",
        )
    )

    result = await client.structured_json("Extract memories from text")

    assert result == {"facts": [{"title": "Runtime", "content": "Uses uv"}]}
    assert client.messages[0]["role"] == "system"
    assert "JSON" in client.messages[0]["content"]
    assert client.messages[1] == {"role": "user", "content": "Extract memories from text"}


@pytest.mark.asyncio
async def test_structured_json_rejects_invalid_json():
    client = FakeQwenClient(
        ChatResponse(
            content="not json",
            tool_calls=[],
            usage={},
            model="fake-qwen",
            finish_reason="stop",
        )
    )

    with pytest.raises(QwenStructuredJSONError, match="valid JSON"):
        await client.structured_json("Extract memories from text")


@pytest.mark.asyncio
async def test_structured_json_wraps_api_failures():
    client = FakeQwenClient(error=RuntimeError("auth failed"))

    with pytest.raises(QwenStructuredJSONError, match="Qwen request failed"):
        await client.structured_json("Extract memories from text")
