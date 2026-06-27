class FakeExtractionQwen:
    async def structured_json(self, prompt: str, **kwargs):
        return {
            "facts": [
                {
                    "title": "Runtime",
                    "content": "Project uses uv",
                    "confidence": 0.9,
                    "provenance": "Project uses uv",
                }
            ],
            "decisions": [
                {
                    "title": "MCP transport",
                    "content": "Use stdio MCP for local agents",
                    "confidence": 0.8,
                    "provenance": "Use stdio MCP",
                }
            ],
            "procedures": [
                {
                    "title": "Run checks",
                    "content": "Run uv run pytest tests/ -q",
                    "confidence": 0.7,
                    "provenance": "Run uv run pytest",
                }
            ],
        }


class FailingExtractionQwen:
    async def structured_json(self, prompt: str, **kwargs):
        raise RuntimeError("qwen unavailable")


def test_memory_extract_stores_valid_candidates_and_returns_capsule(memory_repo):
    from agentos.mcp.tools import MemoryToolHandlers

    handlers = MemoryToolHandlers(repository=memory_repo, qwen_client=FakeExtractionQwen())

    response = handlers.memory_extract(
        text="Project uses uv. Use stdio MCP. Run uv run pytest tests/ -q.",
        project="demo",
        source="unit-test",
    )

    assert response["ok"] is True
    assert response["errors"] == []
    assert [item["kind"] for item in response["items"]] == ["fact", "decision", "procedure"]
    assert response["capsule"]["facts"][0]["key"] == "Runtime"
    search = handlers.memory_search(query="stdio", project="demo", limit=5)
    assert any(item["kind"] == "decision" for item in search["items"])
    assert any(item["kind"] == "procedure" for item in search["items"])


def test_memory_extract_returns_recoverable_error_without_writes(memory_repo):
    from agentos.mcp.tools import MemoryToolHandlers

    handlers = MemoryToolHandlers(repository=memory_repo, qwen_client=FailingExtractionQwen())

    response = handlers.memory_extract(text="Decision: use MCP", project="demo")

    assert response["ok"] is False
    assert response["items"] == []
    assert response["errors"] == ["Qwen extraction failed: qwen unavailable"]
    assert handlers.memory_search(query="MCP", project="demo")["items"] == []
