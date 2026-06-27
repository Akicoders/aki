import pytest

from agentos.qwen.extraction import QwenMemoryExtractor


class FakeStructuredQwen:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error

    async def structured_json(self, prompt: str, **kwargs):
        if self.error:
            raise self.error
        return self.response


@pytest.mark.asyncio
async def test_extractor_groups_valid_candidates_by_kind():
    extractor = QwenMemoryExtractor(
        FakeStructuredQwen(
            {
                "facts": [
                    {
                        "title": "Runtime",
                        "content": "Project uses uv",
                        "confidence": 0.9,
                        "provenance": "uses uv",
                    }
                ],
                "decisions": [
                    {
                        "title": "MCP transport",
                        "content": "Use stdio MCP",
                        "confidence": 0.8,
                        "provenance": "Use stdio",
                    }
                ],
                "procedures": [
                    {
                        "title": "Run tests",
                        "content": "Run uv run pytest tests/ -q",
                        "confidence": 0.7,
                        "provenance": "pytest tests",
                    }
                ],
            }
        )
    )

    result = await extractor.extract("Project uses uv. Use stdio. Run pytest tests.")

    assert result.ok is True
    assert result.errors == []
    assert [candidate.kind for candidate in result.candidates] == [
        "fact",
        "decision",
        "procedure",
    ]
    assert result.grouped["facts"][0].title == "Runtime"


@pytest.mark.asyncio
async def test_extractor_rejects_malformed_candidates_without_valid_results():
    extractor = QwenMemoryExtractor(
        FakeStructuredQwen(
            {
                "facts": [
                    {
                        "title": "",
                        "content": "Missing title",
                        "confidence": 0.9,
                        "provenance": "Missing title",
                    },
                    {
                        "title": "Bad confidence",
                        "content": "Confidence is invalid",
                        "confidence": 1.2,
                        "provenance": "invalid",
                    },
                ],
                "unknown": [
                    {
                        "title": "Unsupported",
                        "content": "Unsupported kind",
                        "confidence": 0.5,
                        "provenance": "Unsupported",
                    }
                ],
            }
        )
    )

    result = await extractor.extract("Malformed response")

    assert result.ok is False
    assert result.candidates == []
    assert any("missing title" in error for error in result.errors)
    assert any("confidence" in error for error in result.errors)
    assert any("unsupported group" in error for error in result.errors)


@pytest.mark.asyncio
async def test_extractor_returns_recoverable_error_when_qwen_fails():
    extractor = QwenMemoryExtractor(FakeStructuredQwen(error=RuntimeError("network down")))

    result = await extractor.extract("Decision: use MCP")

    assert result.ok is False
    assert result.candidates == []
    assert result.errors == ["Qwen extraction failed: network down"]
