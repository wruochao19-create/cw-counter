"""Read the visible inventory balance, anchored to the white field and coin."""
import re

import cv2
import numpy as np

from pixel_ocr import model


def wallet_balance(image):
    """Return (field visible, verified amount). Ambiguous fields are unreadable."""
    rgb = np.asarray(image.convert('RGB'))
    scale = min(1, 1100 / image.width)
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    mask = cv2.inRange(small, (243, 243, 243), (255, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    values = []
    visible = False
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < 6 or not 6 <= w / h <= 28 or cv2.contourArea(contour) < .7*w*h:
            continue
        coin = small[y:y+h, max(0, x-2*h):x]
        if not coin.size:
            continue
        gold = cv2.inRange(coin, (150, 95, 0), (255, 240, 100))
        if cv2.countNonZero(gold) < .025*h*h:
            continue
        left, top, right, bottom = [round(v/scale) for v in (x,y,x+w,y+h)]
        unit = rgb[top:bottom, right:min(image.width,right+round(4*h/scale))]
        field = rgb[top:bottom,left:right]
        if not unit.size or not field.size:
            continue
        # MESOS appears immediately to the right of the number in inventory.
        # Read the digits at their natural aspect ratio. A wide, almost empty
        # balance field otherwise gets compressed by the recognition model.
        margin = max(1, field.shape[0]//12)
        inner = field[margin:-margin, margin:-margin]
        ink = np.where(inner.max(axis=2) < 150)
        if not ink[0].size:
            continue
        field = inner[:, max(0,int(ink[1].min())-margin):int(ink[1].max())+margin+1]
        crops = [cv2.resize(crop[:,:,::-1], None, fx=40/field.shape[0],
                            fy=40/field.shape[0], interpolation=cv2.INTER_CUBIC)
                 for crop in (unit,field)]
        reads, _ = model().text_rec(crops)
        if len(reads)!=2 or reads[0][0].strip().upper() != 'MESOS':
            continue
        visible = True
        digits, confidence = reads[1][:2]
        digits = digits.strip()
        if confidence >= .90 and re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)', digits):
            values.append(int(digits.replace(',','')))
    return visible, values[0] if len(values)==1 else None


class WalletCheck:
    def __init__(self):
        self.phase = 'start'
        self.start = self.end = None
        self.previous = None
        self.absent = 0
        self.next_scan = 0.
        self.last_lines = None
        self.last_scan = None
        self.total = 0
        self.uncertain = 0

    def observe(self, visible, amount, now):
        if self.phase == 'done':
            return None
        if self.phase == 'close':
            self.absent = 0 if visible else self.absent + 1
            if self.absent >= 2:
                self.phase = 'end'
            return None
        if not visible or amount is None or amount != self.previous:
            self.previous = amount if visible else None
            return None
        self.previous = None
        if self.phase == 'start':
            self.start = now, amount
            self.phase = 'close'
            return 'wallet_start'
        self.end = now, amount
        self.phase = 'done'
        return 'wallet_end'

    def count_event(self, at, amount, valid):
        if not self.start or at <= self.start[0] or (self.end and at > self.end[0]):
            return
        if valid:
            self.total += amount
        else:
            self.uncertain += 1
