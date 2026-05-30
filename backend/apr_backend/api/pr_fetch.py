from __future__ import annotations

import re
from typing import Annotated

import httpx
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/pr-fetch", tags=["pr-fetch"])

DemoOwnerHeader = Annotated[str, Header(alias="X-Demo-Owner", min_length=1, max_length=255)]

DIFF_CAP = 50_000

_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)")

GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "AI-PR-Review-Assistant",
}


class FetchPrRequest(BaseModel):
    url: str = Field(min_length=1)


class FetchPrResponse(BaseModel):
    title: str
    description: str
    diff_content: str
    project_name: str = ""
    target_branch: str = ""
    developer_name: str = ""


@router.post("")
def fetch_pr(payload: FetchPrRequest, demo_owner: DemoOwnerHeader) -> FetchPrResponse:
    match = _GITHUB_URL_RE.match(payload.url)
    if match is None:
        raise _http_exception(400, "Invalid GitHub PR URL. Expected format: https://github.com/owner/repo/pull/123")

    owner, repo, pull_number = match.group(1), match.group(2), match.group(3)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"

    title, description, project_name, target_branch, developer_name = _fetch_pr_metadata(api_url)
    diff_content = _fetch_pr_diff(api_url)

    return FetchPrResponse(
        title=title,
        description=description,
        diff_content=diff_content[:DIFF_CAP] if len(diff_content) > DIFF_CAP else diff_content,
        project_name=project_name,
        target_branch=target_branch,
        developer_name=developer_name,
    )


def _fetch_pr_metadata(api_url: str) -> tuple[str, str, str, str, str]:
    try:
        response = httpx.get(api_url, headers=GITHUB_API_HEADERS, timeout=httpx.Timeout(15))
    except httpx.TimeoutException:
        raise _http_exception(502, "GitHub API request timed out")
    except httpx.RequestError as exc:
        raise _http_exception(502, f"Failed to reach GitHub API: {exc}")

    if response.status_code == 404:
        raise _http_exception(404, "Pull request not found")
    if response.status_code == 403:
        raise _http_exception(403, "Access to this repository is restricted or rate limited")
    if response.status_code == 429:
        raise _http_exception(429, "GitHub API rate limit exceeded. Try again later.")
    if response.status_code >= 400:
        raise _http_exception(502, f"GitHub API returned status {response.status_code}")

    data = response.json()
    base = data.get("base", {}) or {}
    return (
        data.get("title", ""),
        data.get("body") or "",
        base.get("repo", {}).get("full_name", ""),
        base.get("ref", ""),
        data.get("user", {}).get("login", ""),
    )


def _fetch_pr_diff(api_url: str) -> str:
    headers = {**GITHUB_API_HEADERS, "Accept": "application/vnd.github.v3.diff"}
    try:
        response = httpx.get(api_url, headers=headers, timeout=httpx.Timeout(15))
    except httpx.TimeoutException:
        raise _http_exception(502, "GitHub API request timed out")
    except httpx.RequestError as exc:
        raise _http_exception(502, f"Failed to reach GitHub API: {exc}")

    if response.status_code == 429:
        raise _http_exception(429, "GitHub API rate limit exceeded. Try again later.")
    if response.status_code >= 400:
        raise _http_exception(502, f"GitHub API returned status {response.status_code}")

    return response.text


def _http_exception(status_code: int, detail: str):
    from fastapi import HTTPException
    return HTTPException(status_code=status_code, detail=detail)
