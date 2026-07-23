"""Run the local Tokdash checkout as the Windows scheduled-task service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

source_root = Path(__file__).resolve().parent
sys.path.insert(0, str(source_root / "src"))
# Scan the mission workspace and the Codex Documents workspace where older
# projects (including 不苟屋长线) live. Project status still requires TASKS.md.
default_roots = [source_root.parent, Path(r"F:\OneDrive\文档")]
os.environ.setdefault("TOKDASH_PROJECT_ROOTS", os.pathsep.join(str(p) for p in default_roots))

log_path = Path(os.environ.get("LOCALAPPDATA", source_root)) / "Tokdash" / "tokdash-local.log"
log_path.parent.mkdir(parents=True, exist_ok=True)
log = log_path.open("a", encoding="utf-8", buffering=1)
sys.stdout = log
sys.stderr = log
sys.argv = ["tokdash", "serve", "--bind", "127.0.0.1", "--port", "55423", "--no-open"]

from tokdash.cli import main

raise SystemExit(main())
