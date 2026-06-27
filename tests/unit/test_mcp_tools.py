import pytest

from agentos.mcp.server import create_mcp_server
from agentos.mcp.tools import MemoryToolHandlers, list_tool_names
from agentos.memory.models import EventType, MemoryEvent, MemoryFact


def test_mcp_server_exposes_five_tool_schemas(memory_repo):
    server = create_mcp_server(handlers=MemoryToolHandlers(repository=memory_repo))

    tools = server._tool_manager.list_tools()


    assert sorted(tool.name for tool in tools) == [
        "memory_context",
        "memory_explain",
        "memory_extract",
        "memory_save",
        "memory_search",
    ]
    assert sorted(list_tool_names()) == sorted(tool.name for tool in tools)


def test_memory_context_returns_capsule(memory_repo):
    memory_repo.upsert_fact(
        MemoryFact(key="package_manager", value="uv", scope="project:demo", confidence=0.9)
    )
    handlers = MemoryToolHandlers(repository=memory_repo)

    response = handlers.memory_context(project="demo", query="package", limit=5)

    assert response["ok"] is True
    assert response["project"] == "demo"
    assert response["errors"] == []
    assert response["capsule"]["facts"][0]["key"] == "package_manager"
    assert "uv" in response["capsule"]["rendered"]


def test_memory_search_returns_ranked_facts_and_events(memory_repo):
    memory_repo.upsert_fact(MemoryFact(key="runtime", value="Python 3.11", scope="project:demo"))
    memory_repo.add_event(
        MemoryEvent(type=EventType.DECISION, project="demo", content="Use stdio MCP server")
    )
    handlers = MemoryToolHandlers(repository=memory_repo)

    response = handlers.memory_search(query="Python", project="demo", limit=10)

    assert response["ok"] is True
    assert response["project"] == "demo"
    assert response["errors"] == []
    assert response["items"][0]["kind"] == "fact"
    assert response["items"][0]["title"] == "runtime"
    assert any(item["kind"] == "decision" for item in response["items"])


@pytest.mark.parametrize(
    ("kind", "stored_kind"),
    [("fact", "fact"), ("decision", "decision"), ("procedure", "procedure")],
)
def test_memory_save_persists_supported_kinds(memory_repo, kind, stored_kind):
    handlers = MemoryToolHandlers(repository=memory_repo)

    response = handlers.memory_save(
        kind=kind,
        title="Run checks",
        content="Run uv run pytest tests/ -q",
        project="demo",
        confidence=0.8,
    )

    assert response["ok"] is True
    assert response["project"] == "demo"
    assert response["errors"] == []
    assert response["memory"]["kind"] == stored_kind
    assert response["memory"]["title"] == "Run checks"


def test_memory_save_rejects_invalid_kind_without_write(memory_repo):
    handlers = MemoryToolHandlers(repository=memory_repo)

    response = handlers.memory_save(
        kind="preference",
        title="Theme",
        content="Use dark mode",
        project="demo",
    )

    assert response["ok"] is False
    assert response["project"] == "demo"
    assert "Unsupported memory kind" in response["errors"][0]
    assert memory_repo.search_facts("Theme", scope="project:demo") == []


def test_qwen_dependent_tools_return_graceful_errors(memory_repo):
    handlers = MemoryToolHandlers(repository=memory_repo)

    extract = handlers.memory_extract(text="Decision: use MCP", project="demo")
    explain = handlers.memory_explain(query="MCP", project="demo")

    assert extract == {
        "ok": False,
        "project": "demo",
        "errors": ["Qwen extraction not yet implemented"],
        "items": [],
    }
    assert explain == {
        "ok": False,
        "project": "demo",
        "errors": ["Qwen extraction not yet implemented"],
        "items": [],
    }
