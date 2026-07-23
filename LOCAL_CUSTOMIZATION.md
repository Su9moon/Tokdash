# Local customization

This checkout is the active Tokdash runtime on this PC. The Windows `Tokdash` scheduled task runs `run_local.py`, which serves `http://127.0.0.1:55423` from this source tree.

## Projects page

- Dashboard: `/projects`
- API: `/api/projects`
- Project discovery: `TOKDASH_PROJECT_ROOTS` (defaults to this checkout's parent directory)
- Add `.tokdash-project.json` at a project root when the Tokdash session project name differs from the folder name:

```json
{"aliases": ["folder-name", "tokdash-session-project-name"]}
```

Task-level costs are shown only when `tasks/TASK-xxx.md` has `Tokdash session IDs: <id>[, <id>]`. The `save-tokens` Skill obtains the current ID from the local API when it starts a task.
