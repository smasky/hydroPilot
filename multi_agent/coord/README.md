# coord

This is the current simplified collaboration template.

Only the minimum required files are kept by default:

```text
coord/
  board.md
  handoff-summary.md
  tasks/
    T-001.md
  updates/
    c1.md
    w1.md
```

## Usage Principles

- `tasks/` defines tasks
- `updates/w1.md` stores the worker's formal completion result
- `updates/c1.md` stores the coordinator's scan and escalation record
- `board.md` shows the current overall state
- `handoff-summary.md` is used for stage handoff

## Current Rules

- the `worker` mainly focuses on execution
- permission requests are exposed through recent pane output
- the `coordinator` performs low-frequency scans of worker pane and `.md`
- the `worker` writes its `.md` only after completion
