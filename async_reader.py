"""Single-flight notification OCR, serialized with its tracker controls.

Only this worker touches the wrapped reader. The calling/UI thread owns public
snapshots and never waits for OCR in read/reset/set_profile/rebase. The bounded
finish call is reserved for settling already captured frames at stop or pause.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from dataclasses import dataclass
import time


@dataclass
class _Reading:
    generation: int
    events: list
    gap: bool
    image: object
    timestamp: float
    lines: list
    diagnostics: dict


class AsyncNotificationReader:
    def __init__(self, real_reader):
        self._reader = real_reader
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='CW-Notifications')
        self._generation = 0
        self._pending = None
        self._controls = deque()
        self._finish_future = None
        self._finish_generation = None
        self._finished = False
        self._closed = False
        self.profile = deepcopy(getattr(real_reader, 'profile', None))
        self.last_lines = []
        self.last_image = None
        self.last_timestamp = None
        self.last_diagnostics = {}

    @property
    def busy(self):
        """A caller can skip creating another screenshot while OCR is running."""
        return (self._finish_future is not None or
                self._pending is not None and not self._pending.done())

    @staticmethod
    def _valid(callback):
        try:
            return callback is None or bool(callback())
        except Exception:
            return False

    def _run_read(self, image, timestamp, generation, valid):
        if generation != self._generation or self._closed:
            return None
        if not self._valid(valid):
            self._reader.reset()
            return None
        started = time.monotonic()
        try:
            events, gap = self._reader.read(image, timestamp)
        except Exception:
            if generation != self._generation or self._closed:
                return None
            raise
        # A foreground/geometry change during OCR invalidates the whole frame,
        # including the tracker's effects. Reset here on the same worker thread.
        if not self._valid(valid):
            self._reader.reset()
            return None
        if generation != self._generation or self._closed:
            return None
        diagnostics = deepcopy(getattr(self._reader, 'last_diagnostics', {}))
        diagnostics['async_processing_ms'] = round((time.monotonic()-started)*1000, 1)
        return _Reading(generation, deepcopy(events), gap, image, timestamp,
                        deepcopy(getattr(self._reader, 'last_lines', [])), diagnostics)

    def _check_controls(self):
        while self._controls and self._controls[0].done():
            self._controls.popleft().result()

    def _publish(self, reading):
        if reading is None or reading.generation != self._generation:
            return None
        self.last_image = reading.image
        self.last_timestamp = reading.timestamp
        self.last_lines = reading.lines
        self.last_diagnostics = reading.diagnostics
        return reading.events, reading.gap

    def read(self, image, timestamp, valid=None):
        """Poll the previous frame, or submit this frame, without waiting.

        While a read is running, new images are ignored rather than queued.
        A returned tuple refers to last_image/last_timestamp, not the new image.
        Delivery does not submit another image: the caller may rebase/reset in
        response to those lines, and the next UI tick submits the next frame.
        """
        if self._closed or self._finish_future is not None:
            return None
        self._check_controls()
        if self._pending is not None:
            if not self._pending.done():
                return None
            future, self._pending = self._pending, None
            return self._publish(future.result())
        self._finished = False
        self._pending = self._executor.submit(self._run_read, image, timestamp,
                                               self._generation, valid)
        return None

    def _control(self, method, *args):
        if self._closed:
            return
        self._generation += 1
        self._finish_future = None
        self._finish_generation = None
        self._finished = False
        self.last_lines = []
        self.last_image = None
        self.last_timestamp = None
        self.last_diagnostics = {}
        self._controls.append(self._executor.submit(method, *args))

    def reset(self):
        self._control(self._reader.reset)

    def set_profile(self, profile):
        if self._closed:
            return
        self.profile = deepcopy(profile)
        self._control(self._reader.set_profile, deepcopy(profile))

    def rebase(self, old_box, new_box):
        self._control(self._reader.rebase, deepcopy(old_box), deepcopy(new_box))

    def _run_finish(self, generation, pending):
        events = []
        if pending is not None:
            # This task is submitted behind pending on the same single worker;
            # retrieving its result cannot wait for another running task.
            reading = pending.result()
            if reading is not None and reading.generation == generation:
                events.extend(reading.events)
        if generation != self._generation or self._closed:
            return []
        events.extend(self._reader.finish())
        return deepcopy(events)

    def finish(self, timeout=3.0):
        """Settle one outstanding frame and tracker tail, at most three seconds.

        A timeout returns an empty list. Retrying finish retrieves that same
        operation once; it never schedules duplicate tracker settlement.
        """
        if self._closed or self._finished:
            return []
        self._check_controls()
        if self._finish_future is None:
            pending, self._pending = self._pending, None
            self._finish_generation = self._generation
            self._finish_future = self._executor.submit(self._run_finish,
                                                        self._generation, pending)
        try:
            events = self._finish_future.result(timeout=max(0.0, min(3.0, float(timeout))))
        except TimeoutError:
            return []
        self._finish_future = None
        self._finished = True
        return events if self._finish_generation == self._generation else []

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._pending = None
        self._finish_future = None
        self._controls.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
