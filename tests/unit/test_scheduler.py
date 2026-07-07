import asyncio
from datetime import datetime, timedelta, UTC
import pytest
from agentos.memory.models import EventType, MemoryEvent
from agentos.memory.repository import MemoryRepository
from agentos.skills.scheduler import run_task_dispatcher, SchedulerSkill


@pytest.mark.asyncio
async def test_scheduler_runs_due_tasks_and_ignores_future_ones(memory_repo: MemoryRepository):
    # 1. Create a reminder in the past (1 minute ago)
    past_time = datetime.now(UTC) - timedelta(minutes=1)
    event_past = MemoryEvent(
        type=EventType.TASK,
        project="scheduler_test",
        content="This is due now",
        meta={
            "reminder_id": "rem_past_01",
            "run_at": past_time.isoformat(),
            "status": "scheduled",
        },
        source="scheduler",
    )
    memory_repo.add_event(event_past)

    # 2. Create a reminder in the future (10 minutes from now)
    future_time = datetime.now(UTC) + timedelta(minutes=10)
    event_future = MemoryEvent(
        type=EventType.TASK,
        project="scheduler_test",
        content="This is in the future",
        meta={
            "reminder_id": "rem_future_02",
            "run_at": future_time.isoformat(),
            "status": "scheduled",
        },
        source="scheduler",
    )
    memory_repo.add_event(event_future)

    # 3. Create an active cron job
    past_cron_time = datetime.now(UTC) - timedelta(minutes=10)
    event_cron = MemoryEvent(
        type=EventType.TASK,
        project="scheduler_test",
        content="Cron description",
        meta={
            "reminder_id": "cron_my_job",
            "cron": "*/5 * * * *",  # Every 5 minutes
            "status": "active",
            "name": "my_job",
        },
        source="scheduler",
        timestamp=past_cron_time,
    )
    memory_repo.add_event(event_cron)

    # 4. Run the dispatcher
    messages = []
    def collector(msg):
        messages.append(msg)

    fired = await run_task_dispatcher(memory_repo, print_callback=collector)

    # Expecting 2 fired tasks: the past reminder and the cron job (first run)
    assert fired == 2
    assert any("[Reminder] This is due now" in m for m in messages)
    assert any("[Cron: my_job] Cron description" in m for m in messages)

    # Fetch updated events
    events = memory_repo.search_events("", project="scheduler_test", event_types=[EventType.TASK])
    
    past_updated = next(e for e in events if e.meta.get("reminder_id") == "rem_past_01")
    assert past_updated.meta["status"] == "completed"
    assert "fired_at" in past_updated.meta

    future_updated = next(e for e in events if e.meta.get("reminder_id") == "rem_future_02")
    assert future_updated.meta["status"] == "scheduled"
    assert "fired_at" not in future_updated.meta

    cron_updated = next(e for e in events if e.meta.get("reminder_id") == "cron_my_job")
    assert cron_updated.meta["status"] == "active"
    assert "last_run" in cron_updated.meta
