from agentos.skills.n8n_trigger import N8nTriggerSkill


def test_n8n_trigger_headers_use_correct_header_key():
    # Test without API key
    skill_no_key = N8nTriggerSkill(config={"api_key": ""})
    headers_no_key = skill_no_key._headers()
    assert "Authorization" not in headers_no_key
    assert "X-N8N-API-KEY" not in headers_no_key
    assert headers_no_key["Content-Type"] == "application/json"

    # Test with API key
    skill_with_key = N8nTriggerSkill(config={"api_key": "my-secret-token"})
    headers_with_key = skill_with_key._headers()
    assert "Authorization" not in headers_with_key
    assert headers_with_key["X-N8N-API-KEY"] == "my-secret-token"
    assert headers_with_key["Content-Type"] == "application/json"
