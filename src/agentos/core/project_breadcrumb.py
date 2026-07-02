"""Last-resolved-project breadcrumb: bootstrap .env discovery from an
unrelated cwd. Single JSON pointer, fail-soft, never raises into callers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_BREADCRUMB_PATH = Path.home() / ".aki" / "last-project.json"


def _breadcrumb_path() -> Path:
    # Recomputed per call so a monkeypatched HOME is honored in tests.
    return Path.home() / ".aki" / "last-project.json"


def write_breadcrumb(root_path: Path) -> None:
    """Best-effort persist of the last resolved project root. Never raises."""
    try:
        resolved = root_path.resolve(strict=False)
        target = _breadcrumb_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "root_path": str(resolved),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        target.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        return  # fail-soft: breadcrumb is an optimization, never a hard dep


def read_breadcrumb() -> Optional[Path]:
    """Return the stored project root if present AND still on disk, else None."""
    try:
        raw = _breadcrumb_path().read_text(encoding="utf-8")
        root = Path(json.loads(raw)["root_path"])
        return root if root.is_dir() else None
    except Exception:
        return None
