# Queued Workflow Log

Writes the workflow of every queued job to `<ComfyUI user directory>/queued/<prompt_id>.json`
when the submission's POST /prompt body carries a `prompt_id` (ComfyUI's own frontend does, and
so does the studio adapter) — so the filename is the Job ID shown in the UI. Submissions without
one fall back to `<job number>.json`,
in UI format — the same JSON you get from Workflow → Export, so it opens on the canvas.

Headless: no nodes, no UI, no settings, no dependencies. Installing it and restarting ComfyUI is
the whole configuration.

## Install

Symlink (or copy) this directory into ComfyUI's `custom_nodes/`, then restart ComfyUI:

    ln -s /path/to/workprint-studio/comfyui-nodes/queued-workflow-log \
          /path/to/ComfyUI/custom_nodes/queued-workflow-log

## Implementation note

ComfyUI's documentation covers node classes, new HTTP routes, and custom WebSocket messages; it
documents no server-side hook on the queue-submission path. This pack uses
`PromptServer.instance.add_on_prompt_handler`, a long-standing but undocumented hook in ComfyUI
core, invoked at the top of the `POST /prompt` route.
