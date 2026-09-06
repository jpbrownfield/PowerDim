"""Pure sliding-window detector for topmost-reassertion z-order fights.

No Win32 dependency: the caller records a correction each time it actually had
to reassert topmost (i.e. something else displaced the overlay). If corrections
happen faster than a real user/app interaction would explain, another window is
almost certainly fighting us for topmost, and the caller should switch to a
dimming mode that doesn't use window z-order at all (see gamma_backend.py).
"""
import time
from collections import deque
from typing import Callable


class FlickerDetector:
    def __init__(
        self,
        window_seconds: float = 2.0,
        threshold: int = 4,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self._window_seconds = window_seconds
        self._threshold = threshold
        self._now = now_fn
        self._events: deque[float] = deque()

    def record_correction(self) -> bool:
        """Call once per actual topmost reassertion. Returns True once the rate
        of corrections within the sliding window reaches the flicker threshold."""
        now = self._now()
        self._events.append(now)
        while self._events and now - self._events[0] > self._window_seconds:
            self._events.popleft()
        return len(self._events) >= self._threshold

    def reset(self) -> None:
        self._events.clear()
