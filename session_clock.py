"""Monotonic foreground map time, independent of OCR digits and kill counts."""


class MapClock:
    def __init__(self):
        self.seconds=0.
        self.last=None

    def observe(self,now,active):
        if self.last is not None and now<self.last:return
        if active:
            if self.last is not None and now-self.last<=2:
                self.seconds+=now-self.last
            self.last=now
        else:
            self.last=None
