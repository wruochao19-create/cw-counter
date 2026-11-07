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
