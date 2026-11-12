`user-exp35.png` is a cropped notification region from the user's supplied screenshot
`codex-clipboard-6ef0d81c-55fa-46f9-9fd2-f4c3ec781d10.png`.
Ground truth is the visible white notification `You received EXP (+35)`.
Crop is (905, 560, 1052, 699) in the supplied 1179×903 screenshot.
It deliberately retains the compressed glyphs and complex background that the old reader failed on.
No screenshot of a running game is captured during tests.

`user-exp17-13-15.png` is cropped at (901, 534, 1036, 655) from the user screenshot
`codex-clipboard-e0aa7932-95b4-40d9-a63d-667259a9bce5.png`.
User-corrected top-to-bottom ground truth is 17, 13, 15.
It is already reduced inside a calibration-window screenshot and retains the green overlay.
The regression requires ambiguous digits to be rejected, not all three values to be recovered.

`user-map-road.png` is the visible minimap title from the same screenshot,
cropped at (129, 130, 293, 171). Ground truth: The Road to the Dungeon.
Both the street label and the actual map title are retained to test disambiguation.

Automatic-region regression samples retain a larger lower-right area without saving whole screenshots:

- `auto-search-exp35.png`: client crop (134,126,1051,700) from the EXP35 screenshot,
  then crop (458,172,917,574) in that client preview. Reconstructed canvas is 917×574.
- `auto-search-faded.png`: client crop (128,112,1036,678) from the 17/13/15 screenshot,
  then crop (454,170,908,566). Reconstructed canvas is 908×566.

The remaining canvas is black. Both default search regions and detected regions fall inside
the retained original pixels. Tests use the real model, not mocked OCR, for these samples.

`user-hud-name.png`: crop (342,650,444,678) of the user's supplied
`codex-clipboard-e0aa7932-95b4-40d9-a63d-667259a9bce5.png`.
Ground truth: job Assassin, character AncPenguin. Only this small HUD region is retained.

`user-exp-bar.png`: original user-supplied small HUD screenshot
`codex-clipboard-dc8faec3-0372-4b06-b333-30ac0aebd14c.png`.
Ground truth: EXP 26,617 [11.07%]. Real pixels test local OCR, two-input
agreement, automatic field discovery and a 2560px-wide bottom-bar search.


`coin-23-a.png` and `coin-23-b.png` are cropped from frames 6 and 7
of the user diagnostic `20261106-112200-057925`, rectangle (145,305,510,338).
Both show the same +23 mesos pickup. They verify the fast row OCR against
real outlined game-font pixels without retaining the full game screen.


`user-wallet-real.png` is a small balance-only crop from the user's visible
inventory on 2026-11-11. Ground truth is 627,949 mesos. It reproduces OCR
reading MESOS as MESO and the thousands comma as a dot.
`user-hud-native.png` is the numeric HUD field discovered through the
application's normal visible-desktop capture and reader on the same date.
Ground truth is EXP 210,233 [58.90%]. The integration test places it in a
window with its blank left edge off-screen and verifies dashboard updates.
