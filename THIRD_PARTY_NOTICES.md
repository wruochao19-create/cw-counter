# Third-party sources

- `vendor/msgwatch.py` and `assets/msg_font.npz` derive from [Javipen/maple-exp-overlay](https://github.com/Javipen/maple-exp-overlay), commit recorded in `vendor/UPSTREAM.txt`. The MIT notice is retained as `vendor/LICENSE.msgwatch`; local patches are documented in `vendor/PATCHES.md`.
- `assets/en-rec.onnx` is an English PP-OCRv3 model; origin and checksum are recorded in `assets/OCR-SOURCE.md`. The PaddleOCR project uses Apache-2.0. Preserve the model source notice when redistributing.
- `assets/monsters.json` records the OSMS catalogue snapshot origin, mirror, retrieval time and source checksum in its metadata. It is a community snapshot, not official live server data.
- CustomTkinter (MIT), darkdetect (BSD-3-Clause), RapidOCR (Apache-2.0), ONNX Runtime (MIT), Pillow and the remaining pinned dependencies are installed from PyPI. Their package distributions include their own license notices. They are not included as copied binary environments in the source archive.
- `tests/data` contains small cropped regression samples supplied during development. Full user screenshots, recordings, session CSVs and diagnostic archives are excluded from the source archive.

This private source package does not grant a new license for third-party game artwork or data.
