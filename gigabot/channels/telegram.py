"""Telegram channel implementation using python-telegram-bot with SaluteSpeech STT."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from telegram import BotCommand, Update, ReplyParameters
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from gigabot.bus.events import OutboundMessage
from gigabot.bus.queue import MessageBus
from gigabot.channels.base import BaseChannel
from gigabot.config.schema import TelegramConfig, SaluteSpeechConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-safe HTML."""
    if not text:
        return ""

    # 1. Protect code blocks
    code_blocks: list[str] = []

    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    # 2. Protect inline code
    inline_codes: list[str] = []

    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)

    # 3. Strip markdown headers
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)

    # 4. Strip blockquotes
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)

    # 5. Escape HTML entities
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Bold **text** / __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 8. Italic _text_ (avoid matching inside identifiers like some_var_name)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 10. Bullet lists
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 11. Restore inline code
    for i, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks
    for i, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def _split_message(content: str, max_len: int = 4096) -> list[str]:
    """Split content into chunks within max_len, preferring line breaks."""
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos == -1:
            pos = cut.rfind(" ")
        if pos == -1:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


# ---------------------------------------------------------------------------
# SaluteSpeech token / transcription
# ---------------------------------------------------------------------------

SALUTE_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
SALUTE_STT_URL = "https://smartspeech.sber.ru/rest/v1/speech:recognize"


class _SaluteTokenCache:
    """Stores an OAuth token and its expiry for SaluteSpeech."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.expires_at: float = 0.0

    @property
    def valid(self) -> bool:
        return self.token is not None and time.time() < self.expires_at


_salute_cache = _SaluteTokenCache()


async def _get_salute_token(cfg: SaluteSpeechConfig) -> str | None:
    """Obtain (or reuse cached) SaluteSpeech OAuth token."""
    if _salute_cache.valid:
        return _salute_cache.token

    if not cfg.client_id or not cfg.client_secret:
        return None

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                SALUTE_OAUTH_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid.uuid4()),
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": cfg.scope,
                },
                auth=(cfg.client_id, cfg.client_secret),
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            _salute_cache.token = data["access_token"]
            _salute_cache.expires_at = time.time() + data.get("expires_in", 1800) - 60
            return _salute_cache.token
    except Exception as e:
        logger.error("Failed to obtain SaluteSpeech token: {}", e)
        return None


async def _transcribe_voice(
    file_path: Path,
    cfg: SaluteSpeechConfig,
) -> str | None:
    """Send an audio file to SaluteSpeech STT API and return the transcribed text."""
    token = await _get_salute_token(cfg)
    if not token:
        return None

    try:
        audio_bytes = file_path.read_bytes()
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                SALUTE_STT_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "audio/ogg;codecs=opus",
                },
                params={"model": cfg.stt_model},
                content=audio_bytes,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", [])
            if results:
                return results[0].get("normalized_text") or results[0].get("text", "")
            return None
    except Exception as e:
        logger.error("SaluteSpeech transcription failed: {}", e)
        return None


# ---------------------------------------------------------------------------
# TelegramChannel
# ---------------------------------------------------------------------------

class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.

    Voice transcription is handled via SaluteSpeech (Sber) instead of Groq Whisper.
    """

    name = "telegram"

    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("help", "Show available commands"),
    ]

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        salute_speech_config: SaluteSpeechConfig | None = None,
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self._salute_speech_config = salute_speech_config
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}
        self._typing_tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True

        req = HTTPXRequest(
            connection_pool_size=16,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
        )
        builder = (
            Application.builder()
            .token(self.config.token)
            .request(req)
            .get_updates_request(req)
        )
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(
                self.config.proxy
            )

        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._forward_command))
        self._app.add_handler(CommandHandler("help", self._on_help))

        self._app.add_handler(
            MessageHandler(
                (
                    filters.TEXT
                    | filters.PHOTO
                    | filters.VOICE
                    | filters.AUDIO
                    | filters.Document.ALL
                )
                & ~filters.COMMAND,
                self._on_message,
            )
        )

        logger.info("Starting Telegram bot (polling mode)...")

        await self._app.initialize()
        await self._app.start()

        bot_info = await self._app.bot.get_me()
        logger.info("Telegram bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning("Failed to register bot commands: {}", e)

        await self._app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,
        )

        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False

        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """Send an outbound message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error("Invalid chat_id: {}", msg.chat_id)
            return

        reply_params = None
        if self.config.reply_to_message:
            reply_to_message_id = msg.metadata.get("message_id")
            if reply_to_message_id:
                reply_params = ReplyParameters(
                    message_id=reply_to_message_id,
                    allow_sending_without_reply=True,
                )

        # Send media files
        for media_path in msg.media or []:
            try:
                media_type = self._get_media_type(media_path)
                sender = {
                    "photo": self._app.bot.send_photo,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = (
                    "photo"
                    if media_type == "photo"
                    else media_type
                    if media_type in ("voice", "audio")
                    else "document"
                )
                display_name = self._document_display_name(media_path)
                with open(media_path, "rb") as f:
                    kwargs: dict[str, Any] = {
                        param: f,
                        "reply_parameters": reply_params,
                    }
                    if param == "document":
                        kwargs["filename"] = display_name
                    await sender(chat_id=chat_id, **kwargs)
            except Exception as e:
                filename = Path(media_path).name
                logger.error("Failed to send media {}: {}", media_path, e)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[Failed to send: {filename}]",
                    reply_parameters=reply_params,
                )

        # Send text content
        if msg.content and msg.content != "[empty message]":
            for chunk in _split_message(msg.content):
                try:
                    html = _markdown_to_telegram_html(chunk)
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=html,
                        parse_mode="HTML",
                        reply_parameters=reply_params,
                    )
                except Exception:
                    try:
                        await self._app.bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            reply_parameters=reply_params,
                        )
                    except Exception as e2:
                        logger.error("Error sending Telegram message: {}", e2)

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _on_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        await update.message.reply_text(
            f"Hi {user.first_name}! I'm GigaBot.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command (accessible to all users, bypasses ACL)."""
        if not update.message:
            return
        await update.message.reply_text(
            "GigaBot commands:\n"
            "/new — Start a new conversation\n"
            "/help — Show available commands"
        )

    async def _forward_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Forward slash commands to the bus for unified handling."""
        if not update.message or not update.effective_user:
            return
        await self._handle_message(
            sender_id=self._sender_id(update.effective_user),
            chat_id=str(update.message.chat_id),
            content=update.message.text,
        )

    # ------------------------------------------------------------------
    # Incoming messages
    # ------------------------------------------------------------------

    async def _on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages (text, photos, voice, audio, documents)."""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)

        self._chat_ids[sender_id] = chat_id

        content_parts: list[str] = []
        media_paths: list[str] = []

        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Detect media
        media_file = None
        media_type: str | None = None

        if message.photo:
            media_file = message.photo[-1]
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"

        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                orig_name = getattr(media_file, "file_name", None)
                ext = self._get_extension(
                    media_type,
                    getattr(media_file, "mime_type", None),
                    orig_name,
                )

                media_dir = Path.home() / ".gigabot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)

                if media_type == "file" and orig_name:
                    safe_name = self._safe_filename(orig_name)
                    file_path = media_dir / f"{media_file.file_id[:16]}_{safe_name}"
                else:
                    file_path = media_dir / f"{media_file.file_id[:16]}{ext}"

                await file.download_to_drive(str(file_path))
                media_paths.append(str(file_path))

                # Voice / audio transcription via SaluteSpeech
                if media_type in ("voice", "audio"):
                    transcription = await self._transcribe_voice_message(file_path)
                    if transcription:
                        logger.info(
                            "Transcribed {}: {}...", media_type, transcription[:50]
                        )
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")

                logger.debug("Downloaded {} to {}", media_type, file_path)
            except Exception as e:
                logger.error("Failed to download media: {}", e)
                content_parts.append(f"[{media_type}: download failed]")

        content = "\n".join(content_parts) if content_parts else "[empty message]"
        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)
        self._start_typing(str_chat_id)

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private",
            },
        )

    # ------------------------------------------------------------------
    # Voice transcription (SaluteSpeech)
    # ------------------------------------------------------------------

    async def _transcribe_voice_message(self, file_path: Path) -> str | None:
        """Transcribe a voice/audio file using SaluteSpeech, or return a fallback."""
        if not self._salute_speech_config:
            logger.debug("SaluteSpeech config not provided, skipping transcription")
            return "[Voice message received, SaluteSpeech not configured]"

        cfg = self._salute_speech_config
        if not cfg.client_id or not cfg.client_secret:
            logger.debug("SaluteSpeech credentials missing, skipping transcription")
            return "[Voice message received, SaluteSpeech not configured]"

        result = await _transcribe_voice(file_path, cfg)
        return result

    # ------------------------------------------------------------------
    # Typing indicators
    # ------------------------------------------------------------------

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(
                    chat_id=int(chat_id), action="typing"
                )
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    async def _on_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Log polling / handler errors."""
        logger.error("Telegram error: {}", context.error)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sender_id(user) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    @staticmethod
    def _get_media_type(path: str) -> str:
        """Guess media type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    @staticmethod
    def _document_display_name(media_path: str) -> str:
        """Strip the file_id prefix when displaying a document name."""
        name = Path(media_path).name
        if len(name) > 17 and name[16] == "_":
            return name[17:]
        return name

    @staticmethod
    def _safe_filename(name: str | None, max_len: int = 200) -> str:
        """Sanitize filename: keep only safe chars, strip path components, limit length."""
        if not name or not name.strip():
            return "document"
        safe = "".join(c for c in name if c.isalnum() or c in "._- ")
        safe = safe.strip(" .") or "document"
        return safe[:max_len] if len(safe) > max_len else safe

    def _get_extension(
        self,
        media_type: str | None,
        mime_type: str | None,
        file_name: str | None = None,
    ) -> str:
        """Get file extension from MIME type, file name, or media type fallback."""
        if file_name and "." in file_name:
            return "." + file_name.rsplit(".", 1)[-1].lower()
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "application/pdf": ".pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                "application/msword": ".doc",
                "application/vnd.ms-excel": ".xls",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]
        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type or "", "")
