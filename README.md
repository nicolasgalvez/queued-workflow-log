# Queued Workflow Log

Writes the workflow of every queued job to `<ComfyUI user directory>/queued/`, in UI format —
the same JSON you get from Workflow → Export, so it opens straight onto the canvas.

Headless: no nodes, no UI, no settings, no dependencies. Installing it and restarting ComfyUI is
the whole configuration. Nothing has to be added to a workflow for it to be captured.

## Filenames

`<prompt_id>.json` when the `POST /prompt` body carries a `prompt_id` — ComfyUI's own frontend
sends one, so the filename matches the Job ID shown in the UI. Submissions without one (a bare
API post) fall back to `<job number>.json`.

**A taken name is never overwritten.** If the file exists, the next free index is used:

    42.json      42_1.json      42_2.json ...

This matters because neither name is unique on its own. The queue number restarts at 0 on every
ComfyUI restart, and a `prompt_id` repeats whenever a job is resubmitted — so writing to a taken
name would destroy the earlier run's workflow, which is the one thing this pack exists to
preserve. The file is claimed with `O_CREAT|O_EXCL`, so two submissions racing on the same name
cannot both win it; the loser takes the next index.

## Install

Clone into ComfyUI's `custom_nodes/`, then restart ComfyUI:

    git clone git@github.com:nicolasgalvez/queued-workflow-log.git \
              /path/to/ComfyUI/custom_nodes/queued-workflow-log

Do **not** symlink it from another checkout if ComfyUI runs in Docker — the link target is
outside the container's mount namespace and the symlink dangles.

## Implementation note

ComfyUI's documentation covers node classes, new HTTP routes, and custom WebSocket messages; it
documents no server-side hook on the queue-submission path. This pack uses
`PromptServer.instance.add_on_prompt_handler`, a long-standing but undocumented hook in ComfyUI
core, invoked at the top of the `POST /prompt` route.

## Test

    python3 test_smoke.py
