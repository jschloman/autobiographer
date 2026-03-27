"""Claude-powered code review agent for GitHub pull requests.

Reads CLAUDE.md as engineering standards context, fetches the PR diff via
GitHub API, sends it to Claude for review, and posts the result as a GitHub
PR review with inline comments where possible.

Required environment variables:
    ANTHROPIC_API_KEY: Anthropic API key.
    GITHUB_TOKEN: GitHub token with pull-requests: write permission.
    PR_NUMBER: Pull request number to review.
    REPO: Repository in owner/repo format.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error


def _github_request(
    path: str,
    method: str = "GET",
    body: dict | None = None,
    token: str = "",
) -> dict:
    """Make a GitHub API request and return parsed JSON.

    Args:
        path: API path, e.g. '/repos/owner/repo/pulls/1/files'.
        method: HTTP method.
        body: Optional JSON-serializable request body.
        token: GitHub token.

    Returns:
        Parsed JSON response as a dict or list.
    """
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _fetch_pr_diff(repo: str, pr_number: str, token: str) -> str:
    """Fetch the unified diff for a pull request.

    Args:
        repo: Repository in owner/repo format.
        pr_number: Pull request number.
        token: GitHub token.

    Returns:
        Unified diff as a single string.
    """
    files = _github_request(f"/repos/{repo}/pulls/{pr_number}/files", token=token)
    chunks: list[str] = []
    for f in files:
        filename = f.get("filename", "")
        patch = f.get("patch", "")
        if patch:
            chunks.append(f"--- {filename}\n{patch}")
    return "\n\n".join(chunks)


def _fetch_pr_commits(repo: str, pr_number: str, token: str) -> list[str]:
    """Return commit SHAs for the PR (used for the review commit_id).

    Args:
        repo: Repository in owner/repo format.
        pr_number: Pull request number.
        token: GitHub token.

    Returns:
        List of commit SHAs, most recent last.
    """
    commits = _github_request(
        f"/repos/{repo}/pulls/{pr_number}/commits", token=token
    )
    return [c["sha"] for c in commits]


def _call_claude(standards: str, diff: str, api_key: str) -> str:
    """Send the diff to Claude with engineering standards as context.

    Args:
        standards: Contents of CLAUDE.md.
        diff: Unified diff of the PR.
        api_key: Anthropic API key.

    Returns:
        Claude's review as a markdown string.
    """
    import urllib.request

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2048,
        "system": (
            "You are an expert code reviewer enforcing the engineering standards "
            "in the document below. Review the provided diff strictly against these "
            "standards. Be direct and specific. Reference file names and line numbers "
            "from the diff where relevant.\n\n"
            "Format your response as:\n"
            "## Summary\n"
            "<1-2 sentence overall assessment>\n\n"
            "## Issues\n"
            "<Blocking issues — violations of the standards. If none, write 'None.'>\n\n"
            "## Suggestions\n"
            "<Non-blocking improvements. If none, write 'None.'>\n\n"
            f"---\n\n# Engineering Standards\n\n{standards}"
        ),
        "messages": [
            {
                "role": "user",
                "content": f"Please review this pull request diff:\n\n```diff\n{diff}\n```",
            }
        ],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=data, method="POST"
    )
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    return result["content"][0]["text"]


def _post_review(
    repo: str,
    pr_number: str,
    commit_sha: str,
    body: str,
    token: str,
) -> None:
    """Post a review comment on the pull request.

    Args:
        repo: Repository in owner/repo format.
        pr_number: Pull request number.
        commit_sha: Latest commit SHA on the PR.
        body: Review body markdown text.
        token: GitHub token.
    """
    _github_request(
        f"/repos/{repo}/pulls/{pr_number}/reviews",
        method="POST",
        body={"commit_id": commit_sha, "body": body, "event": "COMMENT"},
        token=token,
    )


def main() -> None:
    """Entry point: orchestrate fetch → review → post."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    repo = os.environ.get("REPO", "")

    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": api_key,
        "GITHUB_TOKEN": github_token,
        "PR_NUMBER": pr_number,
        "REPO": repo,
    }.items() if not v]
    if missing:
        print(f"ERROR: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    standards_path = os.path.join(os.path.dirname(__file__), "..", "CLAUDE.md")
    with open(standards_path) as f:
        standards = f.read()

    print(f"Fetching diff for {repo}#{pr_number}...")
    diff = _fetch_pr_diff(repo, pr_number, github_token)
    if not diff.strip():
        print("No diff found — skipping review.")
        return

    commits = _fetch_pr_commits(repo, pr_number, github_token)
    if not commits:
        print("No commits found — skipping review.")
        return
    head_sha = commits[-1]

    print("Calling Claude for review...")
    review_body = _call_claude(standards, diff, api_key)

    print("Posting review...")
    _post_review(repo, pr_number, head_sha, review_body, github_token)
    print("Done.")


if __name__ == "__main__":
    main()
