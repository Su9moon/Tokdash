"""Local project/task aggregation for the optional Projects dashboard."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

from .sessions import get_sessions_data


def _roots() -> list[Path]:
    raw = os.environ.get("TOKDASH_PROJECT_ROOTS", "")
    return [Path(item.strip()).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def _task_rows(path: Path, project_dir: Path, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    headers: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and any(cell.lower() in {"id", "编号", "task", "任务", "status", "状态", "started", "开始"} for cell in cells):
            headers = {cell.lower(): index for index, cell in enumerate(cells)}
            continue
        if len(cells) >= 4 and (cells[0].startswith("TASK-") or (cells[0] and cells[0] not in {"编号", "ID", "---", "---"} and not set(cells[0]) <= {"-"})):
            # Support both save-tokens' compact table and existing project indexes.
            def col(*names: str, fallback: str = "") -> str:
                for name in names:
                    index = headers.get(name)
                    if index is not None and index < len(cells):
                        return cells[index]
                return fallback
            task = {"id": col("id", "编号", fallback=cells[0]), "title": col("task", "任务", "title", fallback=cells[1]), "status": col("status", "状态", fallback=cells[2]), "started": col("started", "开始", "started_at")}
            task_file = project_dir / "tasks" / f"{task['id']}.md"
            task["completed"] = ""
            task["outcome"] = "unavailable"
            task["rework_count"] = "unavailable"
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
                    elif lower.startswith("outcome:"):
                        task["outcome"] = task_line.split(":", 1)[1].strip()
                    elif lower.startswith("rework count:"):
                        task["rework_count"] = task_line.split(":", 1)[1].strip()
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
            task["duration_minutes"] = None
            if task.get("started") and task.get("completed"):
                try:
                    task["duration_minutes"] = max(0, int((datetime.fromisoformat(task["completed"]) - datetime.fromisoformat(task["started"])).total_seconds() / 60))
                except ValueError:
                    pass
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
        # Do not recursively scan an entire document drive. Project roots are
        # discovered from Tokdash session cwd values; only inspect immediate
        # children here to recognize explicitly adopted folders.
        try:
            for child in root.iterdir():
                if child.is_dir() and (child / "TASKS.md").exists():
                    dirs.add(child)
        except OSError:
            pass
    return sorted(dirs, key=lambda item: item.name.lower())


@lru_cache(maxsize=8)
def get_projects_data(period: str = "365", include_unmanaged: bool = False) -> dict[str, Any]:
    """Return managed projects plus every historical Codex session project."""
    # Parse the Codex history once from the shared 365-day cache. Named periods
    # are narrowed in memory, so switching 7/30/365 days never rescans JSONL.
    sessions_data = get_sessions_data("codex", "365", None, None, include_review_sessions=True)
    sessions = sessions_data.get("sessions", [])
    if period != "365":
        days = int(period) if str(period).isdigit() else 365
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        sessions = [item for item in sessions if str(item.get("last_seen_at", "")) and datetime.fromisoformat(item["last_seen_at"].replace("Z", "+00:00")) >= cutoff]
    projects: list[dict[str, Any]] = []

    # Adopted projects may live outside the configured workspace roots. Trust
    # only paths already recorded by Tokdash and containing an explicit TASKS.md.
    known_dirs = _project_dirs()
    for session in sessions:
        session_path = Path(str(session.get("path") or "")).expanduser()
        if session_path.is_dir() and (session_path / "TASKS.md").exists() and session_path not in known_dirs:
            known_dirs.append(session_path)

    claimed: set[str] = set()
    for project_dir in sorted(known_dirs, key=lambda item: item.name.lower()):
        aliases = _aliases(project_dir)
        claimed.update(aliases)
        matched = [item for item in sessions if str(item.get("project", "")).lower() in aliases]
        tasks = _task_rows(project_dir / "TASKS.md", project_dir, matched)
        valid_tasks = [task for task in tasks if str(task.get("status", "")).strip().lower() not in {"", "unavailable", "未知"}]
        completed_tasks = [task for task in valid_tasks if str(task.get("status", "")).lower() in {"completed", "complete", "done", "已完成", "完成"}]
        measured_tokens = [task["tokens"] for task in tasks if task.get("tokens") is not None]
        measured_costs = [task["cost"] for task in tasks if task.get("cost") is not None]
        durations = [task["duration_minutes"] for task in tasks if task.get("duration_minutes") is not None]
        reworks = [int(task["rework_count"]) for task in tasks if str(task.get("rework_count", "")).isdigit()]
        projects.append(
            {
                "name": project_dir.name,
                "path": str(project_dir),
                "aliases": sorted(aliases),
                "context": (project_dir / "PROJECT_CONTEXT.md").exists(),
                "managed": True,
                "task_count": len(tasks),
                "tasks": tasks,
                "efficiency": {
                    "task_count": len(valid_tasks),
                    "completed_count": len(completed_tasks),
                    "completion_rate": (len(completed_tasks) / len(tasks)) if tasks else None,
                    "duration_minutes": sum(durations) if durations else None,
                    "tokens": sum(measured_tokens) if measured_tokens else None,
                    "cost": sum(measured_costs) if measured_costs else None,
                    "rework_count": sum(reworks) if reworks else None,
                },
                "session_count": len(matched),
                "tokens": sum(int(item.get("tokens") or 0) for item in matched),
                "cost": sum(float(item.get("cost") or 0) for item in matched),
                "sessions": sorted(matched, key=lambda item: str(item.get("last_seen_at", "")), reverse=True),
            }
        )

    if not include_unmanaged:
        return {"period": period, "roots": [str(item) for item in _roots()], "projects": projects, "complete": True}
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
