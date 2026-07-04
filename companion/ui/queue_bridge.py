"""The only thread-safe handoff point between capture-side worker threads and the Tk main
thread. Worker threads call put(); only the Tk poll loop calls drain().
"""

import queue
from typing import Any


class EventBridge:
    def __init__(self, maxsize: int = 0):
        self._q: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    def put(self, item: Any) -> None:
        self._q.put_nowait(item)

    def drain(self) -> list[Any]:
        items = []
        while True:
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                break
        return items
