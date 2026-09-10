# Queued Workflow Log

Writes the workflow of every queued job to `<ComfyUI user directory>/queued/`, in UI format —
the same JSON you get from Workflow → Export, so it opens straight onto the canvas.

Headless: no nodes, no UI, no settings, no dependencies. Installing it and restarting ComfyUI is
the whole configuration. Nothing has to be added to a workflow for it to be captured.

## Filenames

`<datetime>-<hash>.json`, always — millisecond-resolution local time plus a short random
suffix, e.g. `20260909-212733-481-d3f07a.json`. The suffix keeps two same-millisecond
submissions distinct. Never the queue number: it restarts at 0 on every ComfyUI restart,
so `1.json, 2.json…` collide and say nothing about which run they came from.

The file is created with `open(..., "x")`, so an existing log is never truncated. A name
collision raises `FileExistsError`; ComfyUI core catches on_prompt handler errors, logs the
traceback, and the queue proceeds.

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
