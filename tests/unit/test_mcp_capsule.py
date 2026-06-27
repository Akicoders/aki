from agentos.memory.capsule import MemoryCapsule, build_memory_capsule
from agentos.memory.models import EventType, MemoryContext, MemoryEvent, MemoryFact


def test_build_memory_capsule_groups_kinds_and_sources():
    context = MemoryContext(
        facts=[
            MemoryFact(
                key="package_manager",
                value="Use uv for Python commands",
                scope="project:demo",
                source_event_id="evt_source",
            )
        ],
        events=[
            MemoryEvent(
                id="evt_decision",
                type=EventType.DECISION,
                project="demo",
                content="Chose MCP stdio for local agent integration",
                source="architect",
            ),
            MemoryEvent(
                id="evt_procedure",
                type=EventType.TASK,
                project="demo",
                content="Run uv run pytest before committing",
                source="runbook",
                meta={"kind": "procedure"},
            ),
        ],
    )

    capsule = build_memory_capsule(project="demo", context=context, max_chars=1000)

    assert isinstance(capsule, MemoryCapsule)
    assert [fact.key for fact in capsule.facts] == ["package_manager"]
    assert [event.id for event in capsule.decisions] == ["evt_decision"]
    assert [event.id for event in capsule.procedures] == ["evt_procedure"]
    assert "fact:evt_source" in capsule.sources
    assert "event:evt_decision" in capsule.sources
    assert "event:evt_procedure" in capsule.sources
    assert "# Memory capsule: demo" in capsule.rendered
    assert "## Facts" in capsule.rendered
    assert "## Decisions" in capsule.rendered
    assert "## Procedures" in capsule.rendered


def test_build_memory_capsule_bounds_rendered_text():
    context = MemoryContext(
        facts=[
            MemoryFact(
                key=f"fact_{index}",
                value="x" * 120,
                scope="project:demo",
            )
            for index in range(20)
        ]
    )

    capsule = build_memory_capsule(project="demo", context=context, max_chars=320)

    assert len(capsule.rendered) <= 320
    assert capsule.rendered.endswith("…")
