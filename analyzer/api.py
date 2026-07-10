
from __future__ import annotations
import json, time, urllib.error, urllib.request
from typing import Any

API_URL = "https://graphql.anilist.co"
USER_AGENT = "Unofficial-AniList-Taste-Analyzer/1.4"

class AnalyzerError(RuntimeError):
    pass

def graphql(query: str, variables: dict[str, Any], retries: int = 4) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
                if result.get("errors"):
                    messages = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
                    raise AnalyzerError(messages)
                return result["data"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < retries:
                wait = int(exc.headers.get("Retry-After", "10"))
                print(f"AniList rate limit reached; retrying in {wait} seconds...")
                time.sleep(wait)
                continue
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise AnalyzerError(f"AniList returned HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise AnalyzerError(f"Could not connect to AniList: {exc.reason}") from exc
    raise AnalyzerError("AniList request failed after retries.")
