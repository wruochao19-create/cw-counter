"""Synthetic message pixels from the published glyph templates; no game capture."""
import bootstrap
import numpy as np
from PIL import Image
from vendor import msgwatch as mw


def message_frame(lines, gh=20.0):
    """lines bottom-first: (kind, amount, color, brightness)."""
    scale = gh / mw.GH0
    width = 860
    height = round((mw.ROWS - 1) * mw.PITCH + 2 * (mw.HALF + 6))
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    data = np.load(str(bootstrap.ROOT / 'assets' / 'msg_font.npz'))
    for index, (kind, amount, color, brightness) in enumerate(lines):
        center = height - (mw.HALF+6) - index*mw.PITCH
        y = round(center) - 17
        right = width - mw.EDGE_IN
        x = right - mw.BRACKET_W
        tint = np.array([brightness, brightness, brightness if color == 'white' else 0], dtype=float)

        def paint(template, left):
            # Published templates are normalized glyph shapes, not screenshots.
            shape = np.clip(template, 0, 1)
            shape = (shape > 0.40).astype(float)
            h, w = shape.shape
            canvas[y:y+h, left:left+w] = np.maximum(canvas[y:y+h, left:left+w], (shape[:,:,None]*tint).astype(np.uint8))

        for digit in reversed('+'+str(amount)):
            x -= mw.DIGIT_W
            paint(data[f'c{mw.CHARS.index(digit)}'], x)
        x -= mw.BRACKET_W + 120
        paint(data[f'k_{kind}'], x)
        # Closing bracket sets the rightmost visible pixel used by the recognizer.
        canvas[y+3:y+31, right-3:right] = tint.astype(np.uint8)
    image = Image.fromarray(canvas)
    if scale != 1:
        image = image.resize((round(width*scale), round(height*scale)), Image.Resampling.NEAREST)
    return image

