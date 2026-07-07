import pytest
from agentos.mcp.tools import MemoryToolHandlers


class FakeExplainQwen:
    async def structured_json(self, prompt: str, **kwargs):
        return {
            "explanations": [
                {
                    "id": "ignored-by-handler-test",
                    "explanation": "Stored memory says the project uses uv.",
                }
            ]
        }


class FailingExplainQwen:
    async def structured_json(self, prompt: str, **kwargs):
        raise RuntimeError("qwen unavailable")


@pytest.mark.asyncio
async def test_memory_explain_uses_only_stored_memory_content(memory_repo):
    handlers = MemoryToolHandlers(repository=memory_repo, qwen_client=FakeExplainQwen())
    await handlers.memory_save(kind="fact", title="Runtime", content="Project uses uv", project="demo")

    response = await handlers.memory_explain(query="How are checks run?", project="demo")

    assert response["ok"] is True
    assert response["errors"] == []
    assert response["items"][0]["title"] == "Runtime"
    assert response["items"][0]["explanation"] == "Stored memory says the project uses uv."
    assert "pnpm" not in response["items"][0]["explanation"]


@pytest.mark.asyncio
async def test_memory_explain_falls_back_when_qwen_is_unavailable(memory_repo):
    handlers = MemoryToolHandlers(repository=memory_repo, qwen_client=FailingExplainQwen())
    await handlers.memory_save(
        kind="decision",
        title="MCP transport",
        content="Use stdio MCP for local agents",
        project="demo",
    )

    response = await handlers.memory_explain(query="stdio transport", project="demo")

    assert response["ok"] is True
    assert response["errors"] == ["Qwen explanation failed: qwen unavailable"]
    assert response["items"][0]["explanation"] == "Matches query terms: stdio"
    assert "HTTP" not in response["items"][0]["explanation"]
