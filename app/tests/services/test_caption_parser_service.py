"""CaptionParserService orchestration tests — the AI fallback layer on top of
extract_deterministic. Uses httpx.MockTransport so no real network call is made."""

import json

import httpx

from app.services.parser.caption_parser import CaptionParserService


def _client_returning(json_body: dict, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _client_raising() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_no_ai_configured_returns_regex_only_result() -> None:
    service = CaptionParserService(api_key=None, model="unused")
    result = await service.parse("Naruto\nEpisode 5")
    assert result.title == "Naruto"
    assert result.episode_number == 5
    assert result.sources == {"title": "regex", "episode_number": "regex"}


async def test_no_ai_call_when_nothing_missing() -> None:
    client = _client_raising()
    service = CaptionParserService(
        api_key=None, model="unused", http_client=client, ollama_base_url="http://localhost:11434"
    )
    result = await service.parse("Attack on Titan (2013)\nSeason 4 Episode 12\n1080p")
    assert result.missing_fields == []


async def test_ollama_fills_missing_fields() -> None:
    client = _client_returning(
        {"message": {"content": json.dumps({"quality": "1080p", "year": None})}}
    )
    service = CaptionParserService(
        api_key=None, model="unused", http_client=client, ollama_base_url="http://localhost:11434"
    )
    result = await service.parse("Naruto\nEpisode 5")
    assert result.quality == "1080p"
    assert result.sources["quality"] == "ai"
    assert result.year is None


async def test_falls_back_to_anthropic_when_ollama_unreachable() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if "localhost" in request.url.host:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"quality": "720p"}'}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = CaptionParserService(
        api_key="sk-ant-test",
        model="claude-sonnet-5",
        http_client=client,
        ollama_base_url="http://localhost:11434",
    )
    result = await service.parse("Naruto\nEpisode 5")
    assert result.quality == "720p"
    assert result.sources["quality"] == "ai"
    assert len(calls) == 2


async def test_ai_never_overrides_a_regex_resolved_field() -> None:
    client = _client_returning({"message": {"content": json.dumps({"title": "Wrong Title"})}})
    service = CaptionParserService(
        api_key=None, model="unused", http_client=client, ollama_base_url="http://localhost:11434"
    )
    result = await service.parse("Naruto\nEpisode 5")
    assert result.title == "Naruto"


async def test_malformed_ai_json_leaves_result_as_regex_only() -> None:
    client = _client_returning({"message": {"content": "not valid json"}})
    service = CaptionParserService(
        api_key=None, model="unused", http_client=client, ollama_base_url="http://localhost:11434"
    )
    result = await service.parse("Naruto\nEpisode 5")
    assert result.quality is None
    assert "quality" not in result.sources
