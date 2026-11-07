"""Adapter for the MIT-licensed message reader; stricter counting confidence."""
import bootstrap
import uuid
from dataclasses import dataclass
import cv2
import numpy as np
from vendor import msgwatch as mw

cv2.setNumThreads(1)


@dataclass
class Calibration:
    width: int
    height: int
    gh: float = 7.0
    right_offset: float = 7.0
    bottom_offset: float = 154.35
    region: list | None = None
    text_bottom: float | None = None
    text_right: float | None = None

    def box(self):
        if self.region is not None:
            return tuple(self.region)
        scale = self.gh / mw.GH0
        right = self.width - self.right_offset + mw.EDGE_IN * scale
        center = self.height - self.bottom_offset
        bottom = center + (mw.HALF + 6) * scale
        top = center - (mw.ROWS - 1) * mw.PITCH * scale - (mw.HALF + 6) * scale
        return tuple(round(v) for v in (right - mw.AREA_W * scale, top, right, bottom))

    def select(self, first, last):
        x0, x1 = sorted((max(0, min(self.width, round(first[0]))), max(0, min(self.width, round(last[0])))))
        y0, y1 = sorted((max(0, min(self.height, round(first[1]))), max(0, min(self.height, round(last[1])))))
        if x1 - x0 < 60 or y1 - y0 < 12:
            raise ValueError('请拖出至少 60×12 像素的区域，并包含完整提示文字。')
        self.region = [x0, y0, x1, y1]
        self.text_bottom = (mw.HALF + 6) * self.gh / mw.GH0
        self.text_right = mw.EDGE_IN * self.gh / mw.GH0

    def prepare(self, image):
        """Keep capture exactly inside the selected box; pad to the reader's fixed row grid."""
        if self.region is None:
            return image
        from PIL import Image
        scale = self.gh / mw.GH0
        target_h = round((mw.ROWS - 1) * mw.PITCH * scale + 2 * (mw.HALF + 6) * scale)
        target_w = max(image.width, round(mw.AREA_W * scale))
        bottom_margin = self.text_bottom if self.text_bottom is not None else (mw.HALF + 6) * scale
        right_margin = self.text_right if self.text_right is not None else mw.EDGE_IN * scale
        x = round(target_w - mw.EDGE_IN * scale - (image.width - right_margin))
        y = round(target_h - (mw.HALF + 6) * scale - (image.height - bottom_margin))
        canvas = Image.new('RGB', (target_w, target_h))
        canvas.paste(image, (x, y))
        return canvas


def fit_image(width, height, available_width, available_height):
    scale = min(available_width / width, available_height / height)
    return scale, (available_width - width * scale) / 2, (available_height - height * scale) / 2


def locate_text(image, gh):
    """Try to locate a recognized notification within an arbitrary user-drawn region."""
    bgr = cv2.cvtColor(np.asarray(image.convert('RGB')), cv2.COLOR_RGB2BGR)
    s = gh / mw.GH0
    h = round(mw.HALF * s) + round(4 * s)
    font = mw.Font(bootstrap.ROOT / 'assets')
    found = []
    for center in range(h, image.height - h, max(1, round(s * 3))):
        band = bgr[center-h:center+h+1]
        edge, _ = mw.edges(band, s)
        columns = np.nonzero(edge.sum(axis=0) >= max(1, int(2*s)))[0]
        columns = columns[columns >= image.width * .4]
        if not len(columns):
            continue
        ends = [int(columns[-1]) + 1]
        # Include the preceding group when scenery extends past the closing bracket.
        gaps = np.nonzero(np.diff(columns) > max(2, 4*s))[0]
        ends.extend(int(columns[i])+1 for i in gaps[-3:][::-1])
        for right in ends:
            result = font.read(band, s, right)
            if result and result[0] in ('exp', 'bonus', 'mesos') and result[1] is not None:
                found.append((center, right, result))
                break
    if not found:
        return None
    # Adjacent successful probes describe the same text baseline; choose their centre.
    last = max(row[0] for row in found)
    group = [row for row in found if last-row[0] <= max(3, gh*.6)]
    center = float(np.median([row[0] for row in group]))
    right = float(np.median([row[1] for row in group]))
    return image.height-center, image.width-right


class StrictWatcher(mw.MessageWatcher):
    @staticmethod
    def _finish(line, out):
        mw.MessageWatcher._finish(line, out)
        # Never promote the upstream "best of unclear readings" to a confirmed count.
        line.confident = any(t[2] and t[:2] == (line.kind, line.amount) for t in line.tries)
        votes = getattr(line, 'color_votes', [])
        line.color_confident = len(votes) >= 2 and len(set(votes)) == 1
        if line.color_confident:
            line.colour = votes[0]


class Reader:
    def __init__(self, gh=7.0):
        self.gh = gh
        self.font = mw.Font(bootstrap.ROOT / 'assets')
        self.reset()

    def reset(self):
        self.watcher = StrictWatcher(self.font)
        self.generation = uuid.uuid4().hex[:12]
        self.sequence = 0
        self.last_time = None

    def read(self, rgb_image, timestamp):
        gap = self.last_time is not None and timestamp - self.last_time > 0.75
        if gap:
            self.reset()
        self.last_time = timestamp
        bgr = cv2.cvtColor(np.asarray(rgb_image.convert('RGB')), cv2.COLOR_RGB2BGR)
        lines = self.watcher.look(bgr, self.gh, timestamp)
        events = []
        for line in lines:
            self.sequence += 1
            confirmed = bool(getattr(line, 'confident', False) and
                             getattr(line, 'color_confident', False))
            events.append(dict(event_id=f'{self.generation}-{self.sequence}', kind=line.kind,
                               amount=line.amount, color=line.colour,
                               confident=confirmed,
                               note='OCR+颜色一致' if confirmed else 'OCR或颜色缺少可靠确认'))
        return events, gap

    def inspect(self, rgb_image):
        bgr = cv2.cvtColor(np.asarray(rgb_image.convert('RGB')), cv2.COLOR_RGB2BGR)
        rows, _ = self.watcher.rows(bgr, self.gh)
        return [(i, row.colour, row.said) for i, row in enumerate(rows) if row is not None]
