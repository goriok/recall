from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from recall.scheduler.gchat import GChatNotifier


def make_notifier(webhook_url="https://chat.googleapis.com/fake", **kwargs):
    return GChatNotifier(webhook_url=webhook_url, **kwargs)


# --- payload shapes ---

def test_on_start_builds_cards_v2_payload():
    sent: list = []

    async def fake_post(payload):
        sent.append(payload)

    notifier = make_notifier()
    with patch.object(notifier, "_post_card", side_effect=fake_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(notifier.on_start("my-job"))

    assert len(sent) == 1
    payload = sent[0]
    assert "cardsV2" in payload
    card = payload["cardsV2"][0]["card"]
    assert "my-job" in card["header"]["title"]
    assert "iniciando" in card["header"]["title"]


def test_on_result_includes_duration_and_output():
    sent: list = []

    async def fake_post(payload):
        sent.append(payload)

    notifier = make_notifier()
    with patch.object(notifier, "_post_card", side_effect=fake_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            notifier.on_result("my-job", duration_ms=1234, output="done: 42 chunks")
        )

    payload = sent[0]
    card = payload["cardsV2"][0]["card"]
    assert "1234ms" in card["header"]["title"]
    assert "my-job" in card["header"]["title"]
    widgets = card["sections"][0]["widgets"]
    assert any("42 chunks" in w["textParagraph"]["text"] for w in widgets)


def test_on_error_includes_error_message():
    sent: list = []

    async def fake_post(payload):
        sent.append(payload)

    notifier = make_notifier()
    with patch.object(notifier, "_post_card", side_effect=fake_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            notifier.on_error("my-job", error=RuntimeError("connection refused"))
        )

    payload = sent[0]
    card = payload["cardsV2"][0]["card"]
    assert "ERRO" in card["header"]["title"]
    widgets = card["sections"][0]["widgets"]
    assert any("connection refused" in w["textParagraph"]["text"] for w in widgets)


def test_on_error_includes_cause_if_present():
    sent: list = []

    async def fake_post(payload):
        sent.append(payload)

    notifier = make_notifier()
    cause = RuntimeError("timeout")
    err = RuntimeError("http error")
    err.__cause__ = cause

    with patch.object(notifier, "_post_card", side_effect=fake_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(notifier.on_error("j", error=err))

    widgets = sent[0]["cardsV2"][0]["card"]["sections"][0]["widgets"]
    texts = [w["textParagraph"]["text"] for w in widgets]
    assert any("timeout" in t for t in texts)


# --- resilience ---

def test_on_start_does_not_raise_when_webhook_fails():
    notifier = make_notifier()

    async def bad_post(payload):
        raise ConnectionError("network unreachable")

    with patch.object(notifier, "_post_card", side_effect=bad_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(notifier.on_start("j"))
    # no exception propagated


def test_empty_webhook_url_skips_post():
    notifier = make_notifier(webhook_url="")
    # _post_card should never be called
    with patch.object(notifier, "_post_card") as mock_post:
        import asyncio
        asyncio.get_event_loop().run_until_complete(notifier.on_start("j"))
    mock_post.assert_not_called()


# --- truncation ---

def test_output_truncated_to_limit():
    sent: list = []

    async def fake_post(payload):
        sent.append(payload)

    notifier = make_notifier(truncate_at=10)
    with patch.object(notifier, "_post_card", side_effect=fake_post):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            notifier.on_result("j", duration_ms=0, output="a" * 100)
        )

    widgets = sent[0]["cardsV2"][0]["card"]["sections"][0]["widgets"]
    assert all(len(w["textParagraph"]["text"]) <= 10 for w in widgets)
