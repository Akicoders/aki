"""Scheduler/reminders skill."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4
from croniter import croniter

from agentos.skills.base import Skill, SkillResult
from agentos.memory.repository import MemoryRepository, create_event
from agentos.memory.models import EventType

logger = logging.getLogger(__name__)


class SchedulerSkill(Skill):
    name = "scheduler"
    description = "Schedule reminders, recurring tasks, and cron jobs"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.default_tz = config.get("default_timezone", "America/Lima") if config else "America/Lima"
        self._memory = MemoryRepository()

    async def add_reminder(
        self,
        message: str,
        at: str,  # ISO datetime or "in X minutes/hours/days"
        project: str = "personal",
        repeat: Optional[str] = None,  # cron expression
    ) -> SkillResult:
        """Add a one-time or recurring reminder."""
        try:
            # Parse time
            if at.startswith("in "):
                # Relative time: "in 30 minutes", "in 2 hours", "in 1 day"
                parts = at[3:].split()
                if len(parts) >= 2:
                    value = int(parts[0])
                    unit = parts[1]
                    if "minute" in unit:
                        delta = timedelta(minutes=value)
                    elif "hour" in unit:
                        delta = timedelta(hours=value)
                    elif "day" in unit:
                        delta = timedelta(days=value)
                    else:
                        return SkillResult(success=False, error=f"Unknown unit: {unit}")
                    run_at = datetime.utcnow() + delta
                else:
                    return SkillResult(success=False, error="Invalid relative time format")
            else:
                # Absolute time
                run_at = datetime.fromisoformat(at.replace("Z", "+00:00"))

            reminder_id = f"rem_{uuid4().hex[:8]}"
            event = create_event(
                type=EventType.TASK,
                project=project,
                content=message,
                meta={
                    "reminder_id": reminder_id,
                    "run_at": run_at.isoformat(),
                    "repeat": repeat,
                    "status": "scheduled",
                },
                source="scheduler",
            )

            return SkillResult(success=True, data={
                "reminder_id": reminder_id,
                "message": message,
                "run_at": run_at.isoformat(),
                "repeat": repeat,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def list_reminders(self, project: str = "personal", status: str = "scheduled") -> SkillResult:
        """List reminders for a project."""
        try:
            events = self._memory.search_events(
                query="",
                project=project,
                event_types=[EventType.TASK],
                limit=100,
            )
            reminders = []
            for e in events:
                if e.meta.get("status") == status:
                    reminders.append({
                        "reminder_id": e.meta.get("reminder_id"),
                        "message": e.content,
                        "run_at": e.meta.get("run_at"),
                        "repeat": e.meta.get("repeat"),
                        "status": e.meta.get("status"),
                        "created_at": e.timestamp.isoformat(),
                    })
            return SkillResult(success=True, data={"reminders": reminders})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def cancel_reminder(self, reminder_id: str, project: str = "personal") -> SkillResult:
        """Cancel a reminder."""
        try:
            events = self._memory.search_events(
                query="",
                project=project,
                event_types=[EventType.TASK],
                limit=100,
            )
            for e in events:
                if e.meta.get("reminder_id") == reminder_id:
                    e.meta["status"] = "cancelled"
                    self._memory.update_event(e)
                    return SkillResult(success=True, data={"reminder_id": reminder_id})
            return SkillResult(success=False, error=f"Reminder not found: {reminder_id}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def add_cron(self, name: str, cron_expr: str, message: str, project: str = "personal") -> SkillResult:
        """Add a recurring cron job."""
        try:
            # Validate cron expression
            croniter(cron_expr)

            event = create_event(
                type=EventType.TASK,
                project=project,
                content=message,
                meta={
                    "reminder_id": f"cron_{name}",
                    "cron": cron_expr,
                    "status": "active",
                    "name": name,
                },
                source="scheduler",
            )

            return SkillResult(success=True, data={
                "name": name,
                "cron": cron_expr,
                "message": message,
            })
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def list_cron(self, project: str = "personal") -> SkillResult:
        """List active cron jobs."""
        try:
            events = self._memory.search_events(
                query="",
                project=project,
                event_types=[EventType.TASK],
                limit=100,
            )
            crons = []
            for e in events:
                if "cron" in e.meta and e.meta.get("status") == "active":
                    crons.append({
                        "name": e.meta.get("name"),
                        "cron": e.meta.get("cron"),
                        "message": e.content,
                        "next_run": self._next_cron_run(e.meta["cron"]),
                    })
            return SkillResult(success=True, data={"cron_jobs": crons})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    def _next_cron_run(self, cron_expr: str) -> str:
        """Get next run time for cron expression."""
        try:
            cron = croniter(cron_expr, datetime.utcnow())
            return cron.get_next(datetime).isoformat()
        except Exception:
            return "invalid"


async def run_task_dispatcher(repo: MemoryRepository, print_callback: Optional[Callable[[str], None]] = None) -> int:
    """Find and fire pending scheduled tasks and crons."""
    import logging
    from datetime import datetime
    from croniter import croniter
    from agentos.memory.models import EventType
    
    logger = logging.getLogger(__name__)
    now = datetime.utcnow()
    
    events = repo.search_events(
        query="",
        event_types=[EventType.TASK],
        limit=100,
    )
    
    fired_count = 0
    for e in events:
        status = e.meta.get("status")
        
        # 1. Process scheduled reminders
        if status == "scheduled" and "run_at" in e.meta:
            try:
                run_at = datetime.fromisoformat(e.meta["run_at"])
                run_at_naive = run_at.replace(tzinfo=None) if run_at.tzinfo is not None else run_at
                
                if run_at_naive <= now:
                    e.meta["status"] = "completed"
                    e.meta["fired_at"] = now.isoformat()
                    repo.update_event(e)
                    
                    msg = f"🔔 [Reminder] {e.content}"
                    if print_callback:
                        print_callback(msg)
                    else:
                        logger.info(msg)
                    fired_count += 1
            except Exception as ex:
                logger.error(f"Failed to process reminder {e.id}: {ex}")
                
        # 2. Process active cron jobs
        elif status == "active" and "cron" in e.meta:
            try:
                cron_expr = e.meta["cron"]
                last_run_str = e.meta.get("last_run")
                if last_run_str:
                    last_run = datetime.fromisoformat(last_run_str).replace(tzinfo=None)
                else:
                    last_run = e.timestamp.replace(tzinfo=None)
                
                iter = croniter(cron_expr, last_run)
                next_run = iter.get_next(datetime)
                if next_run <= now:
                    e.meta["last_run"] = now.isoformat()
                    repo.update_event(e)
                    
                    msg = f"🔁 [Cron: {e.meta.get('name')}] {e.content}"
                    if print_callback:
                        print_callback(msg)
                    else:
                        logger.info(msg)
                    fired_count += 1
            except Exception as ex:
                logger.error(f"Failed to process cron job {e.id}: {ex}")
                
    return fired_count