"""One-way failover from the primary DeepSeek key to a backup key."""

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI


load_dotenv()
logger = logging.getLogger(__name__)

_primary_key = os.getenv("DEEPSEEK_API_KEY")
if not _primary_key:
    raise RuntimeError("DEEPSEEK_API_KEY is not configured")

_backup_key = os.getenv("DEEPSEEK_API_KEY_BACKUP")


class DeepSeekKeyFailover:
    """Use the primary key until it fails, then stay on the backup key."""

    def __init__(self, primary_key: str, backup_key: str | None) -> None:
        self._primary_client = AsyncOpenAI(
            api_key=primary_key,
            base_url="https://api.deepseek.com",
            max_retries=0,
        )
        self._backup_client = None
        if backup_key and backup_key != primary_key:
            self._backup_client = AsyncOpenAI(
                api_key=backup_key,
                base_url="https://api.deepseek.com",
                max_retries=0,
            )

        self._using_backup = False
        self._switch_lock = asyncio.Lock()

    async def create_chat_completion(self, **kwargs: Any) -> Any:
        """Call DeepSeek; on any primary request error, switch once to backup."""
        if self._using_backup:
            if self._backup_client is None:
                raise RuntimeError("Backup DeepSeek API key is not configured")
            return await self._backup_client.chat.completions.create(**kwargs)

        try:
            return await self._primary_client.chat.completions.create(**kwargs)
        except Exception as primary_error:
            if self._backup_client is None:
                raise

            async with self._switch_lock:
                if not self._using_backup:
                    self._using_backup = True
                    logger.warning(
                        "Primary DeepSeek request failed (%s); switching to backup key.",
                        type(primary_error).__name__,
                    )

            # If this also fails, propagate it. Later calls continue using
            # backup; the primary key is never retried during this process.
            return await self._backup_client.chat.completions.create(**kwargs)


deepseek_failover = DeepSeekKeyFailover(_primary_key, _backup_key)
