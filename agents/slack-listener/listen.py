#!/usr/bin/env python3
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.services.slack_listener import SlackListener
from app.services.event_pipeline import EventPipeline
from app.models.event import EventSource
from app.config import settings

pipeline = EventPipeline()

active_incident_id = os.environ.get('DEFAULT_INCIDENT_ID')


async def on_message(data: dict):
    print(f"Message from {data['user']}: {data['text'][:100]}...")
    if active_incident_id:
        from uuid import UUID
        result = await pipeline.process_text_event(
            incident_id=UUID(active_incident_id),
            content=data['text'],
            source=EventSource.SLACK,
            actor=data['user'],
        )
        for event in result.get("events", []):
            print(f"  -> Created event: {event.type.value} - {event.content[:50]}")


async def on_image(data: dict):
    print(f"Image from {data['user']}: {data.get('filename', 'unknown')}")
    if active_incident_id:
        from uuid import UUID
        result = await pipeline.process_image_event(
            incident_id=UUID(active_incident_id),
            image_data=data['image_data'],
            source=EventSource.SLACK,
            actor=data['user'],
        )
        for event in result.get("events", []):
            print(f"  -> Created event: {event.type.value} - {event.content[:50]}")


async def main():
    listener = SlackListener(
        on_message=on_message,
        on_image=on_image,
    )

    print(f"Starting Slack listener for channel: {settings.SLACK_INCIDENT_CHANNEL}")
    print("Press Ctrl+C to stop.")

    try:
        await listener.start()
    except KeyboardInterrupt:
        await listener.stop()


if __name__ == '__main__':
    asyncio.run(main())
