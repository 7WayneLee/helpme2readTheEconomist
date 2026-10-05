"""Telegram delivery and HTML formatting helpers."""

from .client import TelegramClient, TelegramError, discover_private_chats

__all__ = ["TelegramClient", "TelegramError", "discover_private_chats"]
