from __future__ import annotations

from unittest.mock import patch
from recall.confluence.client import ConfluenceClient, ConfluenceConfig, ConfluencePage


CLOUD_CFG = ConfluenceConfig(
    url="https://org.atlassian.net",
    auth_type="token",
    email="user@org.com",
    token="secret",
)

FAKE_PAGE = ConfluencePage(
    id="111",
    title="Page One",
    space_key="ENG",
    html_body="<p>content</p>",
    url="/wiki/spaces/ENG/pages/111",
    version=1,
)


def test_get_folder_children_delegates_to_get_children():
    client = ConfluenceClient(CLOUD_CFG)

    with patch.object(client, "get_children", return_value=[FAKE_PAGE, FAKE_PAGE]) as mock_gc:
        pages = client.get_folder_children("5835685962")

    mock_gc.assert_called_once_with("5835685962", limit=25)
    assert pages == [FAKE_PAGE, FAKE_PAGE]


def test_get_folder_children_returns_empty_list_on_no_pages():
    client = ConfluenceClient(CLOUD_CFG)

    with patch.object(client, "get_children", return_value=[]):
        pages = client.get_folder_children("0000")

    assert pages == []


def test_get_folder_children_uses_v1_not_v2(monkeypatch):
    """get_folder_children must NOT call _get_v2 — v2 folder/children endpoint is broken."""
    client = ConfluenceClient(CLOUD_CFG)

    v2_calls: list[str] = []

    def bad_v2(*args, **kwargs):
        v2_calls.append("called")
        raise AssertionError("v2 should not be called")

    monkeypatch.setattr(client, "_get_v2", bad_v2, raising=False)

    with patch.object(client, "get_children", return_value=[FAKE_PAGE]):
        client.get_folder_children("999")

    assert not v2_calls


def test_get_folder_children_v1_request_uses_child_page_path():
    """Integration-level: verify the v1 child/page path is hit via get_children."""
    client = ConfluenceClient(CLOUD_CFG)

    captured_paths: list[str] = []
    original_get = client._get

    def spy_get(path, params=None):
        captured_paths.append(path)
        return {"results": []}

    with patch.object(client, "_get", side_effect=spy_get):
        client.get_folder_children("5835685962")

    assert any("5835685962" in p and "child" in p for p in captured_paths)
