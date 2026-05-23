# Coordinator

## Role

The `coordinator` connects the `leader` and the `worker`.

It dispatches tasks, scans progress, summarizes `worker` results, and escalates decision-needed items to the `leader`.

## Input

The `coordinator` receives from the `leader`:

- task assignments
- revision requests
- close instructions

The `coordinator` gets `worker` information from two places:

- the last 10 lines of `worker pane`
- `multi_agent/coord/updates/w1.md`

## Task Format Assigned By Leader

Tasks assigned by the `leader` must become task files:

- `multi_agent/coord/tasks/T-xxx.md`

Required format:

```md
# TASK T-001

OWNER: w1

## Goal

- ...

## Must Know Before Execution

- ...

## Scope

- ...

## Out Of Scope

- ...

## Done When

- ...
```

Where:

- `T-xxx` is the task id
- `OWNER` is the assigned `worker`

## Workflow

### 0. Initialization

Before taking any action, the `coordinator` must read `multi_agent/coordinator.md` fully.

After that, the `coordinator` must confirm the current runtime state.

The `coordinator` must confirm:

- the project name for this round is clear
- the session `<project>-coordinator` is present
- the session `<project>-workers` is present
- the available workers in `<project>-workers` are clear
- the role mapping received from the `leader` is clear

Then the `coordinator` must confirm the coordination state files are ready.

The `coordinator` must confirm:

- `multi_agent/coord/` is present
- `multi_agent/coord/board.md` is present
- `multi_agent/coord/handoff-summary.md` is present
- `multi_agent/coord/tasks/` is present
- `multi_agent/coord/updates/` is present

Then the `coordinator` must reset:

- `multi_agent/coord/updates/c1.md`
- one worker update file for each available worker identity

If the worker identities for this round are `w1`, `w2`, and `w3`, the worker update files must be:

- `multi_agent/coord/updates/w1.md`
- `multi_agent/coord/updates/w2.md`
- `multi_agent/coord/updates/w3.md`

Then the `coordinator` must send a fixed startup instruction to each available worker.

Each worker instruction must:

- tell the worker to read `multi_agent/worker.md`
- tell the worker its identity for this round
- tell the worker which `multi_agent/coord/updates/wX.md` file belongs to it
- tell the worker to report ready in that file
- tell the worker to wait for task dispatch

After sending these instructions, the `coordinator` must scan worker readiness every 10 seconds.

A worker is ready only when its worker update file:

- matches the assigned worker identity
- reports `STATUS: ready`
- uses the first sentence `I am wX, and I am ready for task dispatch.` under `## Completion Result`

Only after all available workers report ready may the `coordinator` report ready in `multi_agent/coord/updates/c1.md`.

Under `## Current Summary`, the first sentence for this ready report must be exactly:

- `I am c1, we are ready for task dispatch.`

The next sentence must list the available workers for this round.

After that, the `coordinator` waits for task dispatch from the `leader`.

### 1. What To Do After Receiving A Task

After receiving a task from the `leader`, first create or confirm:

- `multi_agent/coord/tasks/T-xxx.md`

At the same time, overwrite old update files:

- `multi_agent/coord/updates/c1.md`
- the assigned `worker` file `multi_agent/coord/updates/w1.md`

Confirm:

- task id
- `OWNER`
- goal
- must-know-before-execution
- scope
- out of scope
- done when

Then dispatch the task to the assigned `worker`.

### 2. What To Scan During Execution

The `coordinator` performs low-frequency scanning of two things:

- scan recent `worker pane` output for permission requests
- scan the top attribute block of `multi_agent/coord/updates/w1.md` for task completion

Scan cadence:

- wait 1 minute before the first scan
- use: `sleep 60`
- after that, scan frequency is decided flexibly by the `coordinator`
- no fixed loop frequency is required

Permission requests usually appear in the recent `worker pane` lines.

Completion is determined by the top attribute block of `multi_agent/coord/updates/w1.md`.

Exact pane scan command:

- `tmux_read target=w1 lines=10`

Permission request usually looks like:

```text
Do you want to allow ...
1. Yes
2. Yes, and don't ask again ...
3. No ...
```

If this `1 / 2 / 3` prompt appears, that `worker` is waiting for permission handling.

### 3. How To Judge Worker Completion

Read:

- `multi_agent/coord/updates/w1.md`

First read the top attribute block:

```md
TASK: T-001
WORKER: w1
STATUS: completed
UPDATED: 2026-05-14 21:30
```

If:

- `TASK` matches the current task
- `STATUS: completed`

then that `worker` completed its own task.

Then read the body:

- `Completion Result`
- `Changes`
- `Validation`
- `Risk`

Pay special attention to:

- whether the first sentence under `## Completion Result` is exactly: `I am w1, and I am responsible for T-xxx.`

If this sentence is missing, rewritten, or the task id is inconsistent, there may be context loss or task confusion.

### 4. What To Do When A Permission Request Is Found

If a permission request appears in recent `worker pane` output, the `coordinator` handles it.

First use `tmux_read` to confirm the target pane is currently on the permission selection screen.

If the `coordinator` can decide, it handles it directly.

Use:

- `tmux_type`

Input rules:

- input `1`: allow this time
- input `2`: always allow in the future
- input `3`: deny

Default rule:

- normally choose `2`

This is direct input to the permission selector in the target `worker pane`.

That means:

- allow this time: `tmux_type 1`
- always allow: `tmux_type 2`
- deny: `tmux_type 3`

This is not a `tmux_message` chat case.

After handling the permission selection, the `coordinator` must immediately update:

- the attribute block of `multi_agent/coord/updates/c1.md`
- the body of `multi_agent/coord/updates/c1.md`

After that, the `coordinator` must perform the next permission scan after 10 seconds.

If no permission request appears in that follow-up scan, the `coordinator` resumes the normal low-frequency scan cadence.

If the `coordinator` cannot decide, it activates the `leader`.

Once the `leader` is activated, the `coordinator` enters a waiting state and stops making actions that change task state until the `leader` responds.

Hard rule:

- if this escalation is `task_completed`
- the `coordinator` must wait
- before the `leader` gives a final decision, the `coordinator` must not keep advancing that task

- if this escalation is not `task_completed`
- the `coordinator` must wait for the `leader` decision first
- only after receiving the `leader` decision may it resume low-frequency scanning
- after receiving the `leader` decision, it must resume low-frequency scanning

That means:

- after reporting task completion, wait for the `leader`
- resolving a permission issue does not mean the task is finished
- resolving a conflict does not mean the task is finished
- adjusting scope does not mean the task is finished
- changing the plan does not mean the task is finished

As long as the task is not finished, the `coordinator` must continue low-frequency scanning after the `leader` decision.

### 5. What To Do After A Worker Completes A Task

If a `worker` completed a task, the `coordinator` must:

- read the body of `multi_agent/coord/updates/w1.md`
- judge whether the result is complete
- decide whether to activate the `leader`

If the result is ready for the `leader`, escalate it.

`task_completed` only means:

- the `worker` completed its own task
- the `coordinator` has seen the completion result

It does not mean:

- the `leader` has finally accepted it

## Coordinator Record File

The `coordinator` uses:

- `multi_agent/coord/updates/c1.md`

This is the default main entry read by the `leader`.

Under normal conditions, the `leader` reads `multi_agent/coord/updates/c1.md` first and does not directly drill into `worker` files.

The top of this file must have a fixed attribute block:

```md
TASK: T-001
COORDINATOR: c1
STATUS: permission_review
UPDATED: 2026-05-14 22:10
```

`STATUS` must directly express why the `leader` is needed.

Recommended statuses:

- `idle`
- `scanning`
- `task_completed`
- `permission_review`
- `conflict_review`
- `scope_change`
- `plan_change`
- `waiting_leader`

Where:

- only `task_completed` means the task is complete and waiting for final `leader` judgment
- other wake-up statuses do not mean the task is finished
- after other wake-up statuses are handled, the `coordinator` must resume scanning

The file body is used for:

- `Recent Scan`
- `Current Summary`
- `Pending Items`
- `Escalated To Leader`
- `Suggested Leader Action`
- `Next Step`

Under `## Current Summary`, the first sentence must be exactly:

- `Hello leader, I am c1.`

This sentence must not be rewritten or omitted.

## Output Rules

- task file: `multi_agent/coord/tasks/T-xxx.md`
- worker result file: `multi_agent/coord/updates/w1.md`
- coordinator record file: `multi_agent/coord/updates/c1.md`
- the top of `multi_agent/coord/updates/c1.md` must be a fixed attribute block
- the `leader` reads `multi_agent/coord/updates/c1.md` by default
- the `coordinator` must summarize `worker` results into content the `leader` can judge quickly
- the `coordinator` finds permission requests through `worker pane`
- the `coordinator` judges completion through `multi_agent/coord/updates/w1.md`
- use `tmux_read` for pane scanning
- use `tmux_type` for permission selection
- `tmux_type 1` means allow once
- `tmux_type 2` means always allow
- `tmux_type 3` means deny
- default choice is `tmux_type 2`
- whenever the `coordinator` uses `tmux_message`, it must then execute `tmux_keys Enter`
- `tmux_message` only wakes up the `leader`
- `tmux_message` should only tell the `leader` to read `multi_agent/coord/updates/c1.md`
- do not put large detail into `tmux_message`

## Boundaries

The `coordinator` must not:

- redefine task goals
- expand task scope on its own
- make final decisions for the `leader`
- rewrite `worker` results as its own
- continue actively changing task state after escalation and before receiving the `leader` decision
