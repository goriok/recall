from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import httpx


@dataclass
class GChatNotifier:
    webhook_url: str = field(default_factory=lambda: os.environ.get("GCHAT_WEBHOOK_URL", ""))
    truncate_at: int = 300

    def _build_card(self, card_id: str, title: str, widgets: list[dict]) -> dict:
        return {
            "cardsV2": [
                {
                    "cardId": card_id,
                    "card": {
                        "header": {"title": title},
                        "sections": [{"widgets": widgets}],
                    },
                }
            ]
        }

    def _truncate(self, text: str) -> str:
        return text[: self.truncate_at] if len(text) > self.truncate_at else text

    async def _post_card(self, payload: dict) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.webhook_url, json=payload, timeout=10.0)
            if resp.status_code >= 400:
                raise RuntimeError(f"GChat webhook returned {resp.status_code}")

    async def on_start(self, name: str) -> None:
        if not self.webhook_url:
            return
        payload = self._build_card(
            f"{name}:start",
            f"[recall] rotina '{name}' iniciando",
            [{"textParagraph": {"text": f"job: {name}"}}],
        )
        try:
            await self._post_card(payload)
        except Exception as exc:
            sys.stderr.write(f"[gchat] on_start failed: {exc}\n")

    async def on_result(self, name: str, *, duration_ms: int, output: str) -> None:
        if not self.webhook_url:
            return
        payload = self._build_card(
            f"{name}:result",
            f"[recall] rotina '{name}' concluida em {duration_ms}ms",
            [{"textParagraph": {"text": self._truncate(output)}}],
        )
        try:
            await self._post_card(payload)
        except Exception as exc:
            sys.stderr.write(f"[gchat] on_result failed: {exc}\n")

    async def on_error(self, name: str, *, error: Exception) -> None:
        if not self.webhook_url:
            return
        widgets: list[dict] = [{"textParagraph": {"text": str(error)}}]
        cause = getattr(error, "__cause__", None)
        if cause is not None:
            widgets.append({"textParagraph": {"text": str(cause)}})
        payload = self._build_card(
            f"{name}:error",
            f"[recall] rotina '{name}' ERRO",
            widgets,
        )
        try:
            await self._post_card(payload)
        except Exception as exc:
            sys.stderr.write(f"[gchat] on_error failed: {exc}\n")
