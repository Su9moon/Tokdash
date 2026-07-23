"""Run the local Tokdash checkout as the Windows scheduled-task service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

source_root = Path(__file__).resolve().parent
sys.path.insert(0, str(source_root / "src"))
os.environ.setdefault("TOKDASH_PROJECT_ROOTS", str(source_root.parent))

log_path = Path(os.environ.get("LOCALAPPDATA", source_root)) / "Tokdash" / "tokdash-local.log"
log_path.parent.mkdir(parents=True, exist_ok=True)
log = log_path.open("a", encoding="utf-8", buffering=1)
sys.stdout = log
sys.stderr = log
sys.argv = ["tokdash", "serve", "--bind", "127.0.0.1", "--port", "55423", "--no-open"]

from tokdash.cli import main

raise SystemExit(main())
