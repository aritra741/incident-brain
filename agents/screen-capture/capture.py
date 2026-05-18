#!/usr/bin/env python3
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.screen_capture import ScreenCaptureAgent, KeystrokeTriggeredCapture
from app.services.privacy_pipeline import PrivacyPipeline
from app.services.gemini_service import GeminiService
from app.services.embedding_service import EmbeddingService
from app.services.event_pipeline import EventPipeline
from app.config import settings

import httpx


async def send_to_api(image_bytes: bytes, redacted_text: str):
    async with httpx.AsyncClient() as client:
        files = {'image': ('capture.png', image_bytes, 'image/png')}
        data = {
            'incident_id': os.environ.get('DEFAULT_INCIDENT_ID', ''),
            'source': 'screen',
            'content': redacted_text,
        }
        try:
            response = await client.post(
                f'http://{settings.HOST}:{settings.PORT}/api/events/image',
                files=files,
                data=data,
                timeout=30.0,
            )
            if response.status_code == 200:
                print(f"Sent capture to API: {response.json()}")
            else:
                print(f"API error: {response.status_code}")
        except Exception as e:
            print(f"Failed to send to API: {e}")


async def main():
    privacy = PrivacyPipeline()

    async def on_capture(image_bytes: bytes):
        print("Processing screen capture...")
        redacted_text, sanitized_image = privacy.process_screen_capture(image_bytes)
        print(f"Redacted text length: {len(redacted_text)}")
        await send_to_api(sanitized_image, redacted_text)

    mode = os.environ.get('CAPTURE_MODE', 'interval')

    if mode == 'keystroke':
        agent = KeystrokeTriggeredCapture(
            on_capture=on_capture,
            enabled=True,
        )
        await agent.start()
        print("Keystroke-triggered capture running. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await agent.stop()
    else:
        agent = ScreenCaptureAgent(
            on_capture=on_capture,
            interval=settings.SCREEN_CAPTURE_INTERVAL,
            enabled=True,
        )
        await agent.start()
        print(f"Interval capture running (every {settings.SCREEN_CAPTURE_INTERVAL}s). Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await agent.stop()


if __name__ == '__main__':
    asyncio.run(main())
