"""n8n workflow trigger skill."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from agentos.skills.base import Skill, SkillResult
from agentos.core.config import get_config

logger = logging.getLogger(__name__)


class N8nTriggerSkill(Skill):
    name = "n8n_trigger"
    description = "Trigger n8n workflows and get status"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:5678") if config else "http://localhost:5678"
        self.api_key = config.get("api_key", "") if config else ""
        self.timeout = config.get("timeout", 30) if config else 30

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-N8N-API-KEY"] = self.api_key
        return headers

    async def trigger_workflow(
        self,
        workflow_id: str,
        data: Optional[dict] = None,
        wait: bool = False,
    ) -> SkillResult:
        """Trigger an n8n workflow."""
        try:
            url = f"{self.base_url}/api/v1/workflows/{workflow_id}/execute"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=data or {}, headers=self._headers())
                resp.raise_for_status()
                result = resp.json()

            execution_id = result.get("executionId") or result.get("id")
            return SkillResult(success=True, data={
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "status": result.get("status", "started"),
                "data": result,
            })
        except httpx.HTTPStatusError as e:
            return SkillResult(success=False, error=f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def trigger_webhook(
        self,
        webhook_path: str,
        data: Optional[dict] = None,
        method: str = "POST",
    ) -> SkillResult:
        """Trigger a webhook endpoint."""
        try:
            url = f"{self.base_url}/webhook/{webhook_path}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method == "POST":
                    resp = await client.post(url, json=data or {}, headers=self._headers())
                else:
                    resp = await client.get(url, params=data or {}, headers=self._headers())
                resp.raise_for_status()
                result = resp.json() if resp.content else {}

            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def get_execution_status(self, execution_id: str) -> SkillResult:
        """Get workflow execution status."""
        try:
            url = f"{self.base_url}/api/v1/executions/{execution_id}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                result = resp.json()

            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def list_workflows(self, active_only: bool = True) -> SkillResult:
        """List all workflows."""
        try:
            url = f"{self.base_url}/api/v1/workflows"
            params = {"active": "true"} if active_only else {}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                result = resp.json()

            workflows = result.get("data", result) if isinstance(result, dict) else result
            return SkillResult(success=True, data={"workflows": workflows})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    async def get_workflow(self, workflow_id: str) -> SkillResult:
        """Get workflow details."""
        try:
            url = f"{self.base_url}/api/v1/workflows/{workflow_id}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self._headers())
                resp.raise_for_status()
                result = resp.json()
            return SkillResult(success=True, data=result)
        except Exception as e:
            return SkillResult(success=False, error=str(e))