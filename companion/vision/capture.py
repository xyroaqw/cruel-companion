"""mss-based screen grabbing of the game window's client area. An mss instance is not
thread-safe, so each ScreenGrabber must be created and used on the same thread (the
VisionWorker creates its own inside run()).
"""

import numpy as np

from companion.vision.window import WindowRect


class ScreenGrabber:
    def __init__(self):
        import mss  # local import: only the vision worker thread pays for it

        self._sct = mss.mss()

    def grab(self, rect: WindowRect) -> np.ndarray:
        """Returns the region as a BGR uint8 array (what cv2 expects)."""
        shot = self._sct.grab(
            {"left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height}
        )
        # mss returns BGRA; dropping alpha yields BGR without a channel swap.
        return np.asarray(shot)[:, :, :3]

    def close(self) -> None:
        self._sct.close()
