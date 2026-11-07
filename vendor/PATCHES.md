# Local changes

- Handle a row without a parsed reading instead of unpacking None.
- Record per-frame color votes and require at least two looks before early completion.
- `recognition.StrictWatcher` marks ambiguous OCR/color results as uncertain, even if upstream returns a best guess.

The upstream reader still has heuristic scrolling/color detection. It is not a guarantee of game kill ownership or perfect counting.

