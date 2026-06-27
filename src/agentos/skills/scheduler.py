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
                    self._memory.add_event(e)
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