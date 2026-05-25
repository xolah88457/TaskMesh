"""GitHub App sink — push files and append-only JSONL logs to a user's repo.

Authenticates as the TaskMesh GitHub App. For each push we mint a fresh
installation-scoped access token from the App's private key. Tokens are
cached in process memory keyed by installation_id with a 50-minute TTL so a
single agent run does not hammer GitHub's `/app/installations/{id}/access_tokens`
endpoint.

This module is the destination side of the Agent-Teams data plane: every
generated file, every coordinator decision, every LLM call's audit row lands
in the user's own GitHub repository under `taskmesh/`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

import httpx
import jwt as pyjwt

_log = logging.getLogger(__name__)

GITHUB_APP_ID          = os.environ.get("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
# The private key can be provided either inline (RSA PEM) or as a file path.
if GITHUB_APP_PRIVATE_KEY and os.path.isfile(GITHUB_APP_PRIVATE_KEY):
    try:
        with open(GITHUB_APP_PRIVATE_KEY) as fh:
            GITHUB_APP_PRIVATE_KEY = fh.read()
    except OSError:
        _log.exception("Failed to read GITHUB_APP_PRIVATE_KEY file")
        GITHUB_APP_PRIVATE_KEY = ""

_GITHUB_API   = "https://api.github.com"
_JWT_TTL_SECS = 9 * 60    # GitHub caps App JWTs at 10 minutes
_TOK_TTL_SECS = 50 * 60   # installation tokens are valid 60 min — leave 10 min slack


class GitHubSinkError(Exception):
    """Surface to the API layer as 5xx / 4xx."""

    def __init__(self, code: str, status_code: int = 502, message: str = "") -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or code
        super().__init__(self.message)


# ─── installation token cache ────────────────────────────────────────────────

# installation_id -> (token, expires_at_monotonic)
_token_cache: dict[str, tuple[str, float]] = {}


def is_app_configured() -> bool:
    return bool(GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY)


def _make_app_jwt() -> str:
    """Sign a JWT with the App's private key.

    GitHub accepts JWTs with iss = App ID, iat slightly in the past (clock
    skew), exp at most 10 min in the future.
    """
    if not is_app_configured():
        raise GitHubSinkError("github_app_unconfigured", status_code=503)
    now = int(time.time())
    payload = {
        "iat": now - 30,
        "exp": now + _JWT_TTL_SECS,
        "iss": GITHUB_APP_ID,
    }
    return pyjwt.encode(payload, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


async def _installation_token(installation_id: str) -> str:
    """Return a valid installation access token, fetching one if cache miss/stale."""
    if not installation_id:
        raise GitHubSinkError("invalid_installation_id", status_code=400)
    cached = _token_cache.get(installation_id)
    now = time.monotonic()
    if cached is not None and cached[1] > now + 30:
        return cached[0]

    app_jwt = _make_app_jwt()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code >= 400:
        _log.error("installation token mint failed %s: %s", resp.status_code, resp.text[:200])
        raise GitHubSinkError("token_mint_failed", status_code=502)
    data = resp.json()
    token = data.get("token")
    if not token:
        raise GitHubSinkError("token_missing", status_code=502)
    _token_cache[installation_id] = (token, now + _TOK_TTL_SECS)
    return token


def _invalidate_token(installation_id: str) -> None:
    _token_cache.pop(installation_id, None)


# ─── GitHub REST helpers ─────────────────────────────────────────────────────

def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _gh_request(
    method: str,
    url: str,
    *,
    token: str,
    installation_id: str,
    json_body: dict | None = None,
    expect: tuple[int, ...] = (200,),
) -> dict | None:
    """Make a request to GitHub. On 401 the cached token is invalidated and
    one retry is attempted with a freshly minted token. Other 4xx surface as
    domain errors; 5xx surface with a generic upstream code."""
    body_kwargs = {"json": json_body} if json_body is not None else {}
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=_headers(token), **body_kwargs)
        if resp.status_code in expect:
            if resp.status_code == 204 or not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        if resp.status_code == 401 and attempt == 0:
            _invalidate_token(installation_id)
            token = await _installation_token(installation_id)
            continue
        if resp.status_code == 403:
            retry_after = resp.headers.get("retry-after")
            raise GitHubSinkError(
                "rate_limited" if retry_after else "forbidden",
                status_code=429 if retry_after else 403,
                message=f"github 403: {resp.text[:160]}",
            )
        if resp.status_code == 404:
            raise GitHubSinkError("not_found", status_code=404, message=f"{url}")
        if resp.status_code >= 500:
            raise GitHubSinkError("upstream_5xx", status_code=502, message=f"github {resp.status_code}")
        raise GitHubSinkError(
            "github_error",
            status_code=resp.status_code,
            message=f"github {resp.status_code}: {resp.text[:200]}",
        )
    raise GitHubSinkError("retry_exhausted", status_code=502)


# ─── high-level operations ───────────────────────────────────────────────────

class GitHubSink:
    """One per request — lightweight, holds installation_id + repo coords."""

    def __init__(self, installation_id: str, repo: str, branch: str = "main") -> None:
        if "/" not in repo:
            raise GitHubSinkError("invalid_repo", status_code=400, message=repo)
        self.installation_id = installation_id
        self.owner, self.name = repo.split("/", 1)
        self.branch = branch or "main"

    async def _token(self) -> str:
        return await _installation_token(self.installation_id)

    async def push_files(self, files: list[tuple[str, str]], message: str) -> str:
        """Atomically commit a batch of (path, content) pairs to ``self.branch``.

        Returns the new commit SHA. Uses the Git Data API so the size of the
        batch costs ~5 requests regardless of file count.
        """
        if not files:
            raise GitHubSinkError("empty_batch", status_code=400)
        token = await self._token()
        base = f"{_GITHUB_API}/repos/{self.owner}/{self.name}"
        # 1. resolve current branch SHA
        ref = await _gh_request(
            "GET", f"{base}/git/ref/heads/{self.branch}",
            token=token, installation_id=self.installation_id,
            expect=(200,),
        )
        if ref is None:
            raise GitHubSinkError("branch_missing", status_code=404)
        base_sha = ref["object"]["sha"]
        # 2. base tree
        base_commit = await _gh_request(
            "GET", f"{base}/git/commits/{base_sha}",
            token=token, installation_id=self.installation_id,
            expect=(200,),
        )
        if base_commit is None:
            raise GitHubSinkError("base_commit_missing", status_code=502)
        base_tree_sha = base_commit["tree"]["sha"]
        # 3. new tree
        tree_items = [
            {"path": p, "mode": "100644", "type": "blob", "content": c}
            for (p, c) in files
        ]
        tree = await _gh_request(
            "POST", f"{base}/git/trees",
            token=token, installation_id=self.installation_id,
            json_body={"base_tree": base_tree_sha, "tree": tree_items},
            expect=(201,),
        )
        if tree is None:
            raise GitHubSinkError("tree_create_failed", status_code=502)
        # 4. commit
        commit = await _gh_request(
            "POST", f"{base}/git/commits",
            token=token, installation_id=self.installation_id,
            json_body={"message": message, "tree": tree["sha"], "parents": [base_sha]},
            expect=(201,),
        )
        if commit is None:
            raise GitHubSinkError("commit_create_failed", status_code=502)
        new_sha = commit["sha"]
        # 5. update ref
        await _gh_request(
            "PATCH", f"{base}/git/refs/heads/{self.branch}",
            token=token, installation_id=self.installation_id,
            json_body={"sha": new_sha, "force": False},
            expect=(200,),
        )
        return new_sha

    async def append_jsonl(self, path: str, lines: list[dict[str, Any]], message: str) -> str:
        """Append JSONL lines to a file in the repo.

        Reads the file's current content via the Contents API, appends the new
        lines, and pushes a new commit. Tolerant of missing files — creates one.
        """
        if not lines:
            return ""
        token = await self._token()
        base = f"{_GITHUB_API}/repos/{self.owner}/{self.name}"
        existing = ""
        try:
            resp = await _gh_request(
                "GET", f"{base}/contents/{path}?ref={self.branch}",
                token=token, installation_id=self.installation_id,
                expect=(200,),
            )
            if resp and resp.get("encoding") == "base64":
                existing = base64.b64decode(resp["content"]).decode("utf-8", errors="replace")
        except GitHubSinkError as exc:
            if exc.code != "not_found":
                raise
        new_chunk = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
        combined = (existing.rstrip() + "\n" + new_chunk + "\n").lstrip()
        return await self.push_files([(path, combined)], message)
