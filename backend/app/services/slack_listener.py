import logging
from typing import Optional, Callable, Awaitable
from uuid import UUID

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from ..config import settings

logger = logging.getLogger(__name__)


class SlackListener:
    def __init__(
        self,
        on_message: Callable[[dict], Awaitable[None]],
        on_image: Callable[[dict], Awaitable[None]],
    ):
        self.app = App(
            token=settings.SLACK_BOT_TOKEN,
            signing_secret=settings.SLACK_SIGNING_SECRET,
        )
        self.on_message = on_message
        self.on_image = on_image
        self.handler: Optional[SocketModeHandler] = None
        self._setup_handlers()

    def _setup_handlers(self):
        @self.app.event("message")
        async def handle_message(event: dict, client: WebClient):
            try:
                if event.get("subtype") == "bot_message":
                    return

                channel_id = event.get("channel")
                if channel_id != settings.SLACK_INCIDENT_CHANNEL:
                    return

                text = event.get("text", "")
                user = event.get("user", "unknown")
                ts = event.get("ts")

                files = event.get("files", [])
                if files:
                    for file_info in files:
                        if file_info.get("mimetype", "").startswith("image/"):
                            image_url = file_info.get("url_private")
                            if image_url:
                                response = client.files_info(file=file_info["id"])
                                image_data = response["content"]
                                await self.on_image(
                                    {
                                        "user": user,
                                        "image_data": image_data,
                                        "timestamp": ts,
                                        "channel": channel_id,
                                        "filename": file_info.get("name", "image"),
                                    }
                                )

                if text:
                    await self.on_message(
                        {
                            "user": user,
                            "text": text,
                            "timestamp": ts,
                            "channel": channel_id,
                        }
                    )

            except Exception as e:
                logger.error(f"Error handling Slack message: {e}")

        @self.app.event("file_shared")
        async def handle_file_shared(event: dict, client: WebClient):
            try:
                file_id = event.get("file_id")
                if file_id:
                    response = client.files_info(file=file_id)
                    file_info = response["file"]

                    if file_info.get("mimetype", "").startswith("image/"):
                        image_url = file_info.get("url_private")
                        if image_url:
                            image_data = response["content"]
                            await self.on_image(
                                {
                                    "user": file_info.get("user", "unknown"),
                                    "image_data": image_data,
                                    "timestamp": file_info.get("created"),
                                    "channel": event.get("channel_id"),
                                    "filename": file_info.get("name", "image"),
                                }
                            )
            except Exception as e:
                logger.error(f"Error handling file share: {e}")

    async def start(self):
        try:
            self.handler = SocketModeHandler(
                self.app, settings.SLACK_APP_TOKEN
            )
            logger.info("Starting Slack listener...")
            self.handler.start()
        except Exception as e:
            logger.error(f"Failed to start Slack listener: {e}")
            raise

    async def stop(self):
        if self.handler:
            self.handler.close()
            logger.info("Slack listener stopped")

    async def post_warning_to_channel(self, warning_message: str, channel: str):
        try:
            client = WebClient(token=settings.SLACK_BOT_TOKEN)
            client.chat_postMessage(
                channel=channel,
                text=f"⚠️ *Incident Brain Warning*\n\n{warning_message}",
                unfurl_links=False,
            )
        except Exception as e:
            logger.error(f"Failed to post warning to Slack: {e}")

    async def post_co_responder_to_channel(self, message: str, channel: str):
        try:
            client = WebClient(token=settings.SLACK_BOT_TOKEN)
            client.chat_postMessage(
                channel=channel,
                text=f"🧠 {message}",
                unfurl_links=False,
            )
        except Exception as e:
            logger.error(f"Failed to post co-responder message to Slack: {e}")
