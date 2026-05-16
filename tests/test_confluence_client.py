import pytest
from unittest.mock import patch, MagicMock
from recall.confluence.client import ConfluenceClient, ConfluencePage, ConfluenceConfig


# --- fixtures ---

FAKE_CLOUD_PAGE = {
    "id": "123456",
    "title": "Architecture Overview",
    "space": {"key": "ENG"},
    "body": {"storage": {"value": "<h1>Overview</h1><p>This is the architecture.</p>"}},
    "version": {"number": 5},
    "_links": {"webui": "/wiki/spaces/ENG/pages/123456"},
}

FAKE_CLOUD_CHILDREN = {
    "results": [FAKE_CLOUD_PAGE],
    "limit": 25,
    "size": 1,
    "_links": {},
}

FAKE_SPACE_PAGES = {
    "results": [FAKE_CLOUD_PAGE],
    "limit": 25,
    "size": 1,
    "_links": {},
}


# --- ConfluenceConfig ---

def test_confluence_config_cloud_url():
    cfg = ConfluenceConfig(
        url="https://myorg.atlassian.net",
        auth_type="token",
        email="user@org.com",
        token="secret",
    )
    assert cfg.is_cloud is True


def test_confluence_config_server_url():
    cfg = ConfluenceConfig(
        url="https://confluence.internal.com",
        auth_type="token",
        token="secret",
    )
    assert cfg.is_cloud is False


def test_confluence_config_requires_email_for_cloud():
    with pytest.raises(ValueError, match="email"):
        ConfluenceConfig(
            url="https://myorg.atlassian.net",
            auth_type="token",
            token="secret",
            email="",
        )


# --- ConfluencePage ---

def test_confluence_page_from_api_response():
    page = ConfluencePage.from_api(FAKE_CLOUD_PAGE)
    assert page.id == "123456"
    assert page.title == "Architecture Overview"
    assert page.space_key == "ENG"
    assert "<h1>" in page.html_body


def test_confluence_page_to_markdown():
    page = ConfluencePage.from_api(FAKE_CLOUD_PAGE)
    md = page.to_markdown()
    assert "Architecture Overview" in md
    assert "Overview" in md
    assert "<" not in md  # no raw HTML tags


def test_confluence_page_to_markdown_strips_html():
    page = ConfluencePage(
        id="1",
        title="Test",
        space_key="ENG",
        html_body="<p>Hello <strong>world</strong></p><ul><li>item</li></ul>",
        url="",
        version=1,
    )
    md = page.to_markdown()
    assert "<p>" not in md
    assert "Hello" in md
    assert "world" in md


# --- ConfluenceClient ---

def test_client_get_page_by_id():
    cfg = ConfluenceConfig(url="https://org.atlassian.net", auth_type="token", email="u@org.com", token="t")
    client = ConfluenceClient(cfg)

    with patch.object(client, "_get", return_value=FAKE_CLOUD_PAGE):
        page = client.get_page("123456")

    assert page.id == "123456"
    assert page.title == "Architecture Overview"


def test_client_get_children_of_page():
    cfg = ConfluenceConfig(url="https://org.atlassian.net", auth_type="token", email="u@org.com", token="t")
    client = ConfluenceClient(cfg)

    # first call returns one child, recursive call on the child returns empty
    empty = {"results": [], "limit": 25, "size": 0, "_links": {}}
    with patch.object(client, "_get", side_effect=[FAKE_CLOUD_CHILDREN, empty]):
        pages = client.get_children("123456")

    assert len(pages) == 1
    assert pages[0].id == "123456"


def test_client_get_space_pages():
    cfg = ConfluenceConfig(url="https://org.atlassian.net", auth_type="token", email="u@org.com", token="t")
    client = ConfluenceClient(cfg)

    with patch.object(client, "_get", return_value=FAKE_SPACE_PAGES):
        pages = client.get_space_pages("ENG")

    assert len(pages) == 1
    assert pages[0].space_key == "ENG"


def test_client_get_pages_by_label():
    cfg = ConfluenceConfig(url="https://org.atlassian.net", auth_type="token", email="u@org.com", token="t")
    client = ConfluenceClient(cfg)

    with patch.object(client, "_get", return_value=FAKE_SPACE_PAGES):
        pages = client.get_pages_by_label("architecture")

    assert len(pages) == 1


def test_client_uses_basic_auth_for_cloud(tmp_path):
    cfg = ConfluenceConfig(url="https://org.atlassian.net", auth_type="token", email="u@org.com", token="t")
    client = ConfluenceClient(cfg)
    auth = client._build_auth()
    assert auth == ("u@org.com", "t")


def test_client_uses_bearer_for_server():
    cfg = ConfluenceConfig(url="https://confluence.internal.com", auth_type="token", token="mytoken")
    client = ConfluenceClient(cfg)
    headers = client._build_headers()
    assert "Authorization" in headers
    assert "mytoken" in headers["Authorization"]
