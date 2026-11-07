# Other-computer agent handoff

This is a Windows screen-only desktop tool, version 0.21. Read README.md first.

## Fast setup

1. Use Windows 10/11 x64 and CPython **3.12 x64 with Tcl/Tk**, installed from python.org. No Codex runtime is required. The project must be in a writable local directory, not Program Files or inside a zip.
2. Run `py -3.12 setup_windows.py` in the project root. If the launcher is unavailable, invoke the installed Python 3.12 executable directly. It creates `.venv`, installs pinned binary packages, then runs `doctor.py`.
3. Run `.venv\Scripts\python.exe doctor.py` independently to confirm the bundled model, catalogue and idle UI. This test never enumerates real game windows or captures the screen.
4. Launch `.venv\Scripts\python.exe app.py`, or double-click `Start CW Counter.cmd`. Installation needs internet; ordinary use works offline. Do not launch a real counting session until the user is ready.
5. Tests: `.venv\Scripts\python.exe -m unittest discover -s tests -q`. Tests use cropped fixtures and generated/mock images, not a live game capture. Set `TEMP` and `TMP` to a writable project-local `.tmp` directory if the host sandbox restricts its normal temporary directory.

## Runtime boundaries

- Never modify/read game files, inject code, read process memory, send game input, hook rendering or inspect packets. Capture uses visible desktop pixels and public window geometry. This restriction is intentional.
- No need to copy settings from the old machine: role/map calibration is detected again. Never commit `settings.json`, `sessions`, `diagnostics`, `reports`, `.deps`, `.venv`, `.tmp`, credentials or recordings.
- Only installation and the explicitly invoked catalogue update script use network. OCR models and catalogue ship with the source. Preserve asset files and third-party notices.
- Do not promise exact kill counts or freedom from anti-cheat detection. Group kills, ambiguous EXP, missing frames, task EXP and level transitions remain limitations documented in README.

## Code map

`app.py`: session lifecycle/capture coordination. `windows_capture.py`: Windows desktop capture/own-window occlusion checks. `hud_exp.py`: HUD worker and EXP/notification reconciliation. `exp_progress.py`: independent EXP/hour and level ETA. `pixel_ocr.py`, `candidate_ocr.py`: OCR and notification tracking. `counter.py`: events/CSV. `sidebar_ui.py`, `modern_sidebar.py`, `ui_runtime.py`: main/settings UI, mini layout, themes and private shape font.

Preserve an active session during UI changes. Hiding sections must not reset counts or replace the capture pipeline. Regression samples containing compressed/faded digits intentionally test rejection as well as successful recognition.

## Diagnosis

- `No module named ...`: run setup again and launch the project `.venv` interpreter; do not use the Windows Store alias or another environment.
- Tk missing: reinstall full Python 3.12 x64 including Tcl/Tk. A minimal/embeddable Python build is not the supported setup.
- ONNX DLL load failure: verify x64 Python and install Microsoft's current Visual C++ x64 runtime from its official site if required; preserve the actual error.
- Window starts but values stay blank: counting must be started by the user, CW must be foreground, minimap/EXP bar/notifications visible. Move the floating panel away from OCR regions.
- `.venv` was moved from another PC: recreate it with setup. Virtual environments are machine-local; transfer the clean source zip instead.

Build a clean distributable using `.venv\Scripts\python.exe scripts\package_source.py`. `dist` contains a source zip and SHA256; it is not a standalone executable.

## GitHub publication handoff

The user requested a **private** repository named `cw-counter`. The local Git repository is prepared; do not change visibility to public. If GitHub CLI is installed and the user has completed `gh auth login`, verify with `gh auth status`, then run `gh repo create cw-counter --private --source . --remote origin --push` only if no destination remote/repository already exists. Reuse an existing confirmed destination rather than overwrite it. Verify the remote repository's `isPrivate` property and HEAD commit after push. Never ask the user to paste a token into the chat or commit credentials.
