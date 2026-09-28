# Elvision

Desktop video management system (VMS) built with PySide6. Runs multiple camera
feeds in a grid workspace, applies YOLO-based detection, records events with
snapshots, and exports results to Excel/CSV.

## Features

- **Multi-source cameras** — RTSP, HLS (`.m3u8`), network stream, webcam,
  local video file, and YouTube.
- **Connection resilience** — configurable transport (`tcp`/`udp`), timeouts,
  auto-reconnect with backoff, and per-source buffering.
- **Grid workspace** — `1x1` through `8x8` layouts with automatic pagination
  when the camera count exceeds the visible cell count.
- **AI detection** — fall detection, plus smoke / fire / PPE detection from a
  shared safety model. Each camera can enable or disable individual features.
- **Event center** — events stored in SQLite, with snapshots captured at the
  moment of detection, filterable and exportable to `.xlsx` / `.csv`.
- **Camera groups** — nested groups with favorites, and a sidebar context menu
  for bulk assignment.
- **Plugin system** — drop a module into `plugins/` to extend the app.
- **Dark theme** — Qt stylesheet generated in `app/ui/styles/theme.py`.

## Requirements

- Python 3.10+
- The model weights (see below), required for AI features

## Installation

```bash
pip install -r requirements.txt
```

## Model weights

The `.pt` files are **not** in this repository (they total ~118 MB and are
excluded via `.gitignore`). Download them from Google Drive:

> https://drive.google.com/drive/folders/1Xpq7kdz_1U2NBcq1r4YTTQudDs-YbHgV

The folder contains a `fall_detection/` and a `safety/` subfolder, each holding
the trained `.pt` model. Place them so the final layout matches the paths the
code expects:

```
app/core/ai/weights/
├── fall_detection/
│   └── best.pt
└── safety/
    └── best.pt
```

Concretely:

1. Open the Drive folder and download the `fall_detection` folder.
2. Open the Drive folder and download the `safety` folder.
3. Create `app/core/ai/weights/` if it does not exist yet.
4. Move the downloaded `fall_detection` and `safety` folders into it.

These paths are referenced in `app/core/ai/feature_manager.py:21` and
`app/core/ai/feature_manager.py:27`. If a model file is missing, Ultralytics
cannot resolve the path and AI detection on that camera will fail to start; the
rest of the app (camera management, grid, groups) is unaffected.

## Running

```bash
python main.py
```

`main.py` reads `config.json` on startup. If the file is absent, the defaults
from `AppConfig` are used; it is written to disk when you change settings in
the UI. Every key can also be overridden by an environment variable —
`ELVISION_THEME`, `ELVISION_LOG_LEVEL`, `ELVISION_MAX_CAMERAS`,
`ELVISION_ENABLE_GPU`, and others (see `app/core/configuration/service.py:85`).

## Local state

The following files are generated at runtime and ignored by git:

| Path              | Purpose                              |
| ----------------- | ------------------------------------ |
| `config.json`     | App configuration (window, log level) |
| `settings.json`   | Current workspace layout             |
| `cameras.json`    | Camera definitions                   |
| `groups.json`     | Camera groups                        |
| `data/events.db`  | SQLite event log                     |
| `snapshots/`      | Event snapshots                      |

## Project layout

```
main.py                     Entry point
app/
  core/
    ai/                     Model loading + detection workers
    camera/                 Camera manager, factory, sources/
    configuration/          config.json loader
    events/                 SQLite event store, snapshot capture
    groups/                 Group management
    layout/                 Grid calculation and pagination
    logging/                Log service
    plugins/                Plugin loader
    settings/               settings.json loader
    services/               Snapshot service
    threads/                Threading helpers
  models/                   Dataclasses (CameraInfo, events, layout)
  repositories/             JSON-backed persistence
  ui/
    camera/                 Camera cell widget, video surface, toolbar
    dialogs/                Add camera, groups, settings, confirmations
    events/                 Event center, filters, detail, export
    sidebar/                Camera tree
    styles/                 Dark theme
    toolbar/                Main toolbar
    widgets/                Toasts, status bar, notifications
    workspace/              Grid workspace
  utils/                    Credential masking helpers
plugins/                    Drop-in plugin modules
```

## Notes

Camera URIs may embed credentials (`rtsp://user:pass@host/stream`). These are
masked automatically before logging via `app/utils/security.py` — keep actual
credentials out of committed config files.
