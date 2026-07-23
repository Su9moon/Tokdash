"""Local project/task aggregation for the optional Projects dashboard."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from .sessions import get_sessions_data


def _roots() -> list[Path]:
    raw = os.environ.get("TOKDASH_PROJECT_ROOTS", "")
    return [Path(item.strip()).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def _task_rows(path: Path, project_dir: Path, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0].startswith("TASK-"):
            task = {"id": cells[0], "title": cells[1], "status": cells[2], "started": cells[3]}
            task_file = project_dir / "tasks" / f"{task['id']}.md"
            task["completed"] = ""
            task["updated"] = ""
            linked_ids: list[str] = []
            if task_file.exists():
                task["updated"] = datetime.fromtimestamp(task_file.stat().st_mtime, timezone.utc).isoformat()
                for task_line in task_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    lower = task_line.lower()
                    if lower.startswith("completed:"):
                        task["completed"] = task_line.split(":", 1)[1].strip()
                    elif lower.startswith("updated:"):
                        task["updated"] = task_line.split(":", 1)[1].strip()
                    if task_line.lower().startswith("tokdash session ids:"):
                        linked_ids = [item.strip() for item in task_line.split(":", 1)[1].split(",") if item.strip()]
                        break
            snapshot: dict[str, float] = {}
            if task_file.exists():
                labels = {"tokdash start tokens:": "start_tokens", "tokdash end tokens:": "end_tokens", "tokdash start cost:": "start_cost", "tokdash end cost:": "end_cost"}
                for task_line in task_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    for label, key in labels.items():
                        if task_line.lower().startswith(label):
                            try:
                                snapshot[key] = float(task_line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
            task["session_ids"] = linked_ids
            task["tokens"] = max(0, int(snapshot["end_tokens"] - snapshot["start_tokens"])) if {"start_tokens", "end_tokens"} <= snapshot.keys() else None
            task["cost"] = max(0, snapshot["end_cost"] - snapshot["start_cost"]) if {"start_cost", "end_cost"} <= snapshot.keys() else None
            rows.append(task)
    return rows


def _aliases(project_dir: Path) -> set[str]:
    names = {project_dir.name.lower()}
    config = project_dir / ".tokdash-project.json"
    if not config.exists():
        return names
    try:
        import json
        data = json.loads(config.read_text(encoding="utf-8"))
        names.update(str(name).lower() for name in data.get("aliases", []) if str(name).strip())
    except (OSError, ValueError, TypeError):
        pass
    return names


def _project_dirs() -> list[Path]:
    dirs: set[Path] = set()
    for root in _roots():
        if not root.is_dir():
            continue
        if (root / "TASKS.md").exists():
            dirs.add(root)
        for task_index in root.rglob("TASKS.md"):
            # Ignore dependency/cache trees and avoid turning arbitrary task logs into projects.
            if not {".git", "node_modules", ".venv", "vendor"}.intersection(task_index.parts):
                dirs.add(task_index.parent)
    return sorted(dirs, key=lambda item: item.name.lower())


def get_projects_data(period: str = "365") -> dict[str, Any]:
    """Return managed projects plus every historical Codex session project."""
    sessions_data = get_sessions_data("codex", period, None, None, include_review_sessions=True)
    sessions = sessions_data.get("sessions", [])
    projects: list[dict[str, Any]] = []

    claimed: set[str] = set()
    for project_dir in _project_dirs():
        aliases = _aliases(project_dir)
        claimed.update(aliases)
        matched = [item for item in sessions if str(item.get("project", "")).lower() in aliases]
        tasks = _task_rows(project_dir / "TASKS.md", project_dir, matched)
        projects.append(
            {
                "name": project_dir.name,
                "path": str(project_dir),
                "aliases": sorted(aliases),
                "context": (project_dir / "PROJECT_CONTEXT.md").exists(),
                "managed": True,
                "task_count": len(tasks),
                "tasks": tasks,
                "session_count": len(matched),
                "tokens": sum(int(item.get("tokens") or 0) for item in matched),
                "cost": sum(float(item.get("cost") or 0) for item in matched),
                "sessions": sorted(matched, key=lambda item: str(item.get("last_seen_at", "")), reverse=True),
            }
        )

    unclaimed: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        name = str(session.get("project") or "未命名会话项目").strip() or "未命名会话项目"
        if name.lower() not in claimed:
            unclaimed.setdefault(name, []).append(session)
    for name, matched in unclaimed.items():
        paths = {str(item.get("path") or "").strip() for item in matched}
        project_path = next((item for item in paths if item), None)
        projects.append(
            {
                "name": name,
                "path": project_path,
                "aliases": [name.lower()],
                "context": False,
                "managed": False,
                "task_count": 0,
                "tasks": [],
                "session_count": len(matched),
                "tokens": sum(int(item.get("tokens") or 0) for item in matched),
                "cost": sum(float(item.get("cost") or 0) for item in matched),
                "sessions": sorted(matched, key=lambda item: str(item.get("last_seen_at", "")), reverse=True),
            }
        )

    projects.sort(key=lambda item: int(item["tokens"]), reverse=True)
    return {"period": period, "roots": [str(item) for item in _roots()], "projects": projects}
