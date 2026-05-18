import logging
import asyncio
from typing import Callable, Awaitable, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


class ScreenCaptureAgent:
    def __init__(
        self,
        on_capture: Callable[[bytes], Awaitable[None]],
        interval: int = 30,
        enabled: bool = False,
    ):
        self.on_capture = on_capture
        self.interval = interval
        self.enabled = enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if not self.enabled:
            logger.info("Screen capture agent is disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        logger.info(f"Screen capture agent started (interval: {self.interval}s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Screen capture agent stopped")

    async def _capture_loop(self):
        while self._running:
            try:
                image_bytes = await self._capture_active_terminal()
                if image_bytes:
                    await self.on_capture(image_bytes)
            except Exception as e:
                logger.error(f"Screen capture error: {e}")

            await asyncio.sleep(self.interval)

    async def _capture_active_terminal(self) -> Optional[bytes]:
        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                png_bytes = mss.tools.to_png(
                    screenshot.rgb, screenshot.size
                )
                return png_bytes

        except ImportError:
            logger.warning("mss not installed, screen capture unavailable")
            return None
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            return None

    async def capture_now(self) -> Optional[bytes]:
        return await self._capture_active_terminal()


class KeystrokeTriggeredCapture:
    def __init__(
        self,
        on_capture: Callable[[bytes], Awaitable[None]],
        enabled: bool = False,
    ):
        self.on_capture = on_capture
        self.enabled = enabled
        self._listener = None

    async def start(self):
        if not self.enabled:
            logger.info("Keystroke-triggered capture is disabled")
            return

        try:
            from pynput import keyboard
            import threading

            def on_press(key):
                try:
                    if hasattr(key, "char") and key.char:
                        asyncio.get_event_loop().call_soon_threadsafe(
                            lambda: asyncio.create_task(self._on_keystroke())
                        )
                except Exception:
                    pass

            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.start()
            logger.info("Keystroke-triggered capture started")

        except ImportError:
            logger.warning("pynput not installed, keystroke capture unavailable")
        except Exception as e:
            logger.error(f"Failed to start keystroke capture: {e}")

    async def stop(self):
        if self._listener:
            self._listener.stop()
            logger.info("Keystroke-triggered capture stopped")

    async def _on_keystroke(self):
        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                png_bytes = mss.tools.to_png(
                    screenshot.rgb, screenshot.size
                )
                if png_bytes:
                    await self.on_capture(png_bytes)
        except Exception as e:
            logger.error(f"Keystroke capture failed: {e}")
