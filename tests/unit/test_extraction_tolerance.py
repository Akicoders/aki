from agentos.qwen.extraction import validate_extraction_payload, ExtractionResult, MemoryCandidate


def test_extraction_succeeds_as_long_as_some_candidates_are_valid():
    # One valid item, one completely broken item (missing title)
    payload = {
        "facts": [
            {
                "title": "Valid fact",
                "content": "Valid content",
                "confidence": 0.9,
                "provenance": "Source",
            },
            {
                # Missing title
                "content": "Broken content",
                "confidence": 0.8,
                "provenance": "Source",
            }
        ]
    }

    candidates, errors = validate_extraction_payload(payload)
    
    # We should have exactly 1 valid candidate
    assert len(candidates) == 1
    assert candidates[0].title == "Valid fact"
    
    # We should have captured the error for the broken item
    assert len(errors) > 0
    assert "missing title" in errors[0]

    # ExtractionResult should be ok=True since we got 1 valid candidate
    result = ExtractionResult(ok=len(candidates) > 0, candidates=candidates, errors=errors)
    assert result.ok is True
    assert len(result.candidates) == 1


def test_extraction_fails_when_all_candidates_are_malformed():
    payload = {
        "facts": [
            {
                "title": "",  # broken
                "content": "Broken content",
                "confidence": 0.8,
                "provenance": "Source",
            }
        ]
    }
    candidates, errors = validate_extraction_payload(payload)
    assert len(candidates) == 0
    result = ExtractionResult(ok=len(candidates) > 0, candidates=candidates, errors=errors)
    assert result.ok is False
