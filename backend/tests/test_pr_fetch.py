from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response, TimeoutException, ConnectError

from apr_backend.main import create_app

OWNER = {"X-Demo-Owner": "owner-a"}

VALID_URL = "https://github.com/octocat/hello-world/pull/42"
API_URL = "https://api.github.com/repos/octocat/hello-world/pulls/42"


def _github_mock(title="Fix login bug", body="Fixed the race condition.", diff="diff --git a/src/auth.py\n+fix", diff_status=200):
    """Set up respx mock that routes metadata and diff requests correctly by Accept header."""

    def handler(request):
        accept = request.headers.get("Accept", "")
        if "diff" in accept:
            if diff_status >= 400:
                return Response(diff_status)
            return Response(200, content=diff)
        return Response(200, json={
            "title": title,
            "body": body,
            "base": {"ref": "main", "repo": {"full_name": "octocat/hello-world"}},
            "user": {"login": "octocat"},
        })

    return handler


def _setup_github(route, *, title="Fix login bug", body="Fixed the race condition.",
                  diff="diff --git a/src/auth.py\n+fix", diff_status=200):
    route.get(API_URL).mock(side_effect=_github_mock(title, body, diff, diff_status))


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as tc:
        yield tc


class TestPrFetchSuccess:
    def test_returns_title_description_and_diff(self, client):
        with respx.mock as route:
            _setup_github(route)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Fix login bug"
        assert body["description"] == "Fixed the race condition."
        assert "diff --git" in body["diff_content"]
        assert body["project_name"] == "octocat/hello-world"
        assert body["target_branch"] == "main"
        assert body["developer_name"] == "octocat"

    def test_handles_url_with_trailing_path(self, client):
        with respx.mock as route:
            _setup_github(route, title="T", body="")

            response = client.post("/api/pr-fetch", json={"url": "https://github.com/octocat/hello-world/pull/42/files"}, headers=OWNER)

        assert response.status_code == 200

    def test_handles_url_with_fragment(self, client):
        with respx.mock as route:
            _setup_github(route, title="T", body="")

            response = client.post("/api/pr-fetch", json={"url": "https://github.com/octocat/hello-world/pull/42/files#diff-xxx"}, headers=OWNER)

        assert response.status_code == 200

    def test_null_description_becomes_empty_string(self, client):
        with respx.mock as route:
            _setup_github(route, title="No description", body=None)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        assert response.json()["description"] == ""

    def test_truncates_diff_at_50k_chars(self, client):
        large_diff = "x" * 60_000
        with respx.mock as route:
            _setup_github(route, diff=large_diff)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        assert len(response.json()["diff_content"]) == 50_000

    def test_exact_50k_diff_passes_unchanged(self, client):
        exact_diff = "y" * 50_000
        with respx.mock as route:
            _setup_github(route, diff=exact_diff)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        assert len(response.json()["diff_content"]) == 50_000

    def test_missing_base_user_fields_default_to_empty(self, client):
        with respx.mock as route:
            route.get(API_URL).mock(side_effect=_github_mock(title="T", body="B", diff="d"))

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["project_name"] == "octocat/hello-world"
        assert body["target_branch"] == "main"
        assert body["developer_name"] == "octocat"

    def test_empty_base_user_when_github_returns_minimal(self, client):
        def minimal_handler(request):
            accept = request.headers.get("Accept", "")
            if "diff" in accept:
                return Response(200, content="d")
            return Response(200, json={"title": "Minimal", "body": None})

        with respx.mock as route:
            route.get(API_URL).mock(side_effect=minimal_handler)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 200
        body = response.json()
        assert body["project_name"] == ""
        assert body["target_branch"] == ""
        assert body["developer_name"] == ""


class TestPrFetchErrors:
    def test_invalid_url_not_github(self, client):
        response = client.post("/api/pr-fetch", json={"url": "https://gitlab.com/owner/repo/-/merge_requests/1"}, headers=OWNER)
        assert response.status_code == 400
        assert "Invalid GitHub PR URL" in response.json()["detail"]

    def test_malformed_url(self, client):
        response = client.post("/api/pr-fetch", json={"url": "not-a-url"}, headers=OWNER)
        assert response.status_code == 400
        assert "Invalid GitHub PR URL" in response.json()["detail"]

    def test_github_404(self, client):
        with respx.mock as route:
            route.get(API_URL).respond(404)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 404

    def test_github_403(self, client):
        with respx.mock as route:
            route.get(API_URL).respond(403)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 403
        assert "Access" in response.json()["detail"]

    def test_github_429_rate_limit(self, client):
        with respx.mock as route:
            route.get(API_URL).respond(429)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()

    def test_github_rate_limit_on_diff_request(self, client):
        with respx.mock as route:
            _setup_github(route, diff_status=429)

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 429

    def test_network_timeout(self, client):
        with respx.mock as route:
            route.get(API_URL).mock(side_effect=TimeoutException("timed out"))

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 502
        assert "timed out" in response.json()["detail"].lower()

    def test_network_error(self, client):
        with respx.mock as route:
            route.get(API_URL).mock(side_effect=ConnectError("connection refused"))

            response = client.post("/api/pr-fetch", json={"url": VALID_URL}, headers=OWNER)

        assert response.status_code == 502

    def test_requires_demo_owner(self, client):
        response = client.post("/api/pr-fetch", json={"url": VALID_URL})
        assert response.status_code == 422
