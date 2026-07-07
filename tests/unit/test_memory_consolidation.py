from datetime import datetime, UTC
from agentos.memory.models import EventType, MemoryEvent
from agentos.memory.repository import MemoryRepository


def test_memory_consolidation_deletes_old_events(memory_repo: MemoryRepository):
    project = "test_consolidate"
    
    # 1. Seed 12 events to exceed a max_events limit of 10
    # Make sure we use a unique timestamp for ordering
    for i in range(12):
        event = MemoryEvent(
            type=EventType.USER_PREFERENCE,
            project=project,
            content=f"User preference detail {i}",
            source="user",
            timestamp=datetime(2026, 1, 1, 12, i, 0, tzinfo=UTC),
        )
        memory_repo.add_event(event)

    # Count initial events in database
    with memory_repo.db.session() as session:
        from agentos.memory.models import MemoryEventModel
        from sqlalchemy import select, func
        initial_count = session.execute(
            select(func.count(MemoryEventModel.id)).where(MemoryEventModel.project == project)
        ).scalar()
        assert initial_count == 12

    # 2. Consolidate with max_events = 10 (should process 2 events)
    fact_count = memory_repo.consolidate_project(project, max_events=10)
    assert fact_count == 2

    # 3. Verify that those 2 events are deleted from the database
    with memory_repo.db.session() as session:
        remaining_count = session.execute(
            select(func.count(MemoryEventModel.id)).where(MemoryEventModel.project == project)
        ).scalar()
        assert remaining_count == 10

    # 4. Verify facts were created
    facts = memory_repo.search_facts("", scope=f"project:{project}")
    assert len(facts) == 2
    assert facts[0].value in ("User preference detail 0", "User preference detail 1")
    assert facts[1].value in ("User preference detail 0", "User preference detail 1")

    # 5. Run consolidation again; it must return 0 because event count is now <= max_events (10)
    second_run = memory_repo.consolidate_project(project, max_events=10)
    assert second_run == 0

    # Verify no new facts were duplicated or created
    facts_after = memory_repo.search_facts("", scope=f"project:{project}")
    assert len(facts_after) == 2
