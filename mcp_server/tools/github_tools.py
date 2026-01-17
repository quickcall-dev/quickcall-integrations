"""
GitHub Tools - Pull requests and commits via GitHub API.

Authentication (in priority order):
1. Personal Access Token (PAT) - more permissions, user's default choice
   - Set via connect_github_via_pat command
   - Or GITHUB_TOKEN env var / .quickcall.env file
2. QuickCall GitHub App - fallback if no PAT configured

PAT is preferred because:
- Users have direct control over permissions
- Works with any repository the user has access to
- No GitHub App installation required
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.api_clients.github_client import GitHubClient
from mcp_server.auth import (
    get_credential_store,
    get_github_pat,
    get_github_pat_username,
)
from mcp_server.auth.credentials import _find_project_root, _parse_env_file

logger = logging.getLogger(__name__)


# ============================================================================
# Issue Template Support
# ============================================================================

DEFAULT_ISSUE_TEMPLATE: Dict[str, Any] = {
    "labels": [],
    "body": "## Description\n\n## Details\n",
}


def _load_github_native_templates() -> Dict[str, Dict[str, Any]]:
    """
    Load GitHub native issue templates from .github/ISSUE_TEMPLATE/*.yml.
    Returns dict of template_name -> template_config.
    """
    project_root = _find_project_root()
    if not project_root:
        return {}

    template_dir = project_root / ".github" / "ISSUE_TEMPLATE"
    if not template_dir.exists():
        return {}

    templates = {}
    for template_file in template_dir.glob("*.yml"):
        try:
            with open(template_file) as f:
                config = yaml.safe_load(f) or {}

            # Extract template name (use filename without extension as fallback)
            name = config.get("name", template_file.stem)
            # Use filename stem as key for easier matching
            key = template_file.stem

            # Convert GitHub template format to our format
            templates[key] = {
                "name": name,
                "description": config.get("description", ""),
                "title_prefix": config.get("title", ""),
                "labels": config.get("labels", []),
                "assignees": config.get("assignees", []),
                "body": _github_template_body_to_markdown(config.get("body", [])),
            }
        except Exception as e:
            logger.warning(f"Failed to load GitHub template {template_file}: {e}")

    return templates


def _github_template_body_to_markdown(body: List[Dict[str, Any]]) -> str:
    """Convert GitHub issue template body fields to markdown."""
    if not body:
        return ""

    lines = []
    for field in body:
        field_type = field.get("type", "")
        attrs = field.get("attributes", {})
        label = attrs.get("label", "")

        if field_type in ("textarea", "input"):
            if label:
                lines.append(f"## {label}")
                lines.append("")
            placeholder = attrs.get("placeholder", "")
            if placeholder:
                lines.append(placeholder)
                lines.append("")
        elif field_type == "markdown":
            value = attrs.get("value", "")
            if value:
                lines.append(value)
                lines.append("")

    return "\n".join(lines)


def _get_all_templates() -> Dict[str, Dict[str, Any]]:
    """
    Get all available issue templates from both sources.
    Priority: Custom templates (.quickcall.env) > GitHub native templates
    """
    templates = {}

    # 1. Load GitHub native templates first (lower priority)
    templates.update(_load_github_native_templates())

    # 2. Load custom templates (higher priority, can override)
    template_path = os.getenv("ISSUE_TEMPLATE_PATH")
    if not template_path:
        project_root = _find_project_root()
        if project_root:
            config_path = project_root / ".quickcall.env"
            if config_path.exists():
                env_vars = _parse_env_file(config_path)
                if "ISSUE_TEMPLATE_PATH" in env_vars:
                    template_path = env_vars["ISSUE_TEMPLATE_PATH"]
                    if not Path(template_path).is_absolute():
                        template_path = str(project_root / template_path)

    if template_path:
        try:
            with open(template_path) as f:
                config = yaml.safe_load(f) or {}
            custom_templates = config.get("templates", {})
            for key, tpl in custom_templates.items():
                templates[key] = {
                    "name": key,
                    "description": "",
                    "title_prefix": "",
                    "labels": tpl.get("labels", []),
                    "assignees": tpl.get("assignees", []),
                    "body": tpl.get("body", ""),
                }
        except Exception as e:
            logger.warning(f"Failed to load custom templates: {e}")

    return templates


def _load_issue_template(template_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Load issue template from available sources.

    Sources (in priority order):
    1. Custom templates from ISSUE_TEMPLATE_PATH in .quickcall.env
    2. GitHub native templates from .github/ISSUE_TEMPLATE/*.yml

    Returns defaults if no template found.
    """
    if not template_type:
        return DEFAULT_ISSUE_TEMPLATE

    all_templates = _get_all_templates()

    if template_type in all_templates:
        tpl = all_templates[template_type]
        return {
            "labels": tpl.get("labels", []),
            "assignees": tpl.get("assignees", []),
            "body": tpl.get("body", ""),
            "title_prefix": tpl.get("title_prefix", ""),
        }

    return DEFAULT_ISSUE_TEMPLATE


# Track whether we're using PAT mode for status reporting
_using_pat_mode: bool = False
_pat_source: Optional[str] = None

# Module-level client cache (keyed by token hash for security)
_client_cache: Optional[Tuple[int, GitHubClient]] = None


def _get_client() -> GitHubClient:
    """
    Get the GitHub client using the best available authentication method.

    Authentication priority:
    1. Personal Access Token (PAT) - preferred, more permissions
    2. QuickCall GitHub App - fallback if no PAT

    Uses cached client if token hasn't changed.

    Raises:
        ToolError: If no authentication method is available
    """
    global _using_pat_mode, _pat_source, _client_cache

    store = get_credential_store()

    # Try PAT first (preferred - user has more control)
    pat_token, pat_source_str = get_github_pat()
    if pat_token:
        token_hash = hash(pat_token)

        # Return cached client if token matches
        if _client_cache and _client_cache[0] == token_hash:
            return _client_cache[1]

        _using_pat_mode = True
        _pat_source = pat_source_str
        pat_username = get_github_pat_username()
        logger.info(f"Using GitHub PAT from {pat_source_str}")

        client = GitHubClient(
            token=pat_token,
            default_owner=pat_username,
            installation_id=None,  # No installation ID for PAT
        )
        _client_cache = (token_hash, client)
        return client

    # Fall back to QuickCall GitHub App
    if store.is_authenticated():
        creds = store.get_api_credentials()
        if creds and creds.github_connected and creds.github_token:
            token_hash = hash(creds.github_token)

            # Return cached client if token matches
            if _client_cache and _client_cache[0] == token_hash:
                return _client_cache[1]

            _using_pat_mode = False
            _pat_source = None

            client = GitHubClient(
                token=creds.github_token,
                default_owner=creds.github_username,
                installation_id=creds.github_installation_id,
            )
            _client_cache = (token_hash, client)
            return client

    # No authentication available - provide helpful error message
    _using_pat_mode = False
    _pat_source = None
    _client_cache = None

    if store.is_authenticated():
        # Connected to QuickCall but GitHub not connected
        raise ToolError(
            "GitHub not connected. Options:\n"
            "1. Run connect_github_via_pat with your Personal Access Token (recommended)\n"
            "2. Connect GitHub App at quickcall.dev/assistant\n"
            "3. Set GITHUB_TOKEN environment variable"
        )
    else:
        # Not connected to QuickCall at all
        raise ToolError(
            "GitHub authentication required. Options:\n"
            "1. Run connect_github_via_pat with a Personal Access Token (recommended)\n"
            "2. Run connect_quickcall to use QuickCall (GitHub App + Slack)\n"
            "3. Set GITHUB_TOKEN environment variable\n\n"
            "For PAT: Create token at https://github.com/settings/tokens\n"
            "Required scopes: repo (private) or public_repo (public only)"
        )


def is_using_pat_mode() -> Tuple[bool, Optional[str]]:
    """
    Check if GitHub tools are using PAT mode.

    Returns:
        Tuple of (is_using_pat, source) where source is where the PAT was loaded from.
    """
    return (_using_pat_mode, _pat_source)


def create_github_tools(mcp: FastMCP) -> None:
    """Add GitHub tools to the MCP server."""

    @mcp.tool(tags={"github", "repos"})
    def list_repos(
        limit: int = Field(
            default=20,
            description="Maximum number of repositories to return (default: 20)",
        ),
    ) -> dict:
        """
        List GitHub repositories accessible to the authenticated user.

        Returns repositories sorted by last updated.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            repos = client.list_repos(limit=limit)

            return {
                "count": len(repos),
                "repos": [repo.model_dump() for repo in repos],
            }
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to list repositories: {str(e)}")

    @mcp.tool(tags={"github", "prs"})
    def list_prs(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner (username or org). Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        state: str = Field(
            default="open",
            description="PR state: 'open', 'closed', or 'all' (default: 'open')",
        ),
        limit: int = Field(
            default=20,
            description="Maximum number of PRs to return (default: 20)",
        ),
        detail_level: str = Field(
            default="summary",
            description="'summary' for minimal fields (~200 bytes/PR: number, title, state, author, merged_at, html_url), "
            "'full' for all fields (~2KB/PR). Use 'summary' for large result sets, 'full' for detailed analysis.",
        ),
    ) -> dict:
        """
        List pull requests for a GitHub repository.

        Returns PRs sorted by last updated.
        Use detail_level='summary' (default) to avoid context overflow.
        Use get_prs() to fetch full details for specific PRs.
        """
        try:
            client = _get_client()
            prs = client.list_prs(
                owner=owner,
                repo=repo,
                state=state,
                limit=limit,
                detail_level=detail_level,
            )

            return {
                "count": len(prs),
                "detail_level": detail_level,
                "prs": [pr.model_dump() for pr in prs],
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list pull requests: {str(e)}")

    @mcp.tool(tags={"github", "prs"})
    def get_prs(
        pr_refs: List[dict] = Field(
            ...,
            description="List of PR references. Each item should have 'owner', 'repo', and 'number' keys. "
            "Example: [{'owner': 'org', 'repo': 'myrepo', 'number': 123}, ...]",
        ),
    ) -> dict:
        """
        Get detailed information about one or more pull requests.

        Works for single or multiple PRs - fetches in parallel when multiple.
        Each PR ref needs owner, repo, and number.

        Returns full PR details including additions, deletions, and files changed.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()

            # Validate input
            validated_refs = []
            for ref in pr_refs:
                if not isinstance(ref, dict):
                    raise ToolError(f"Invalid PR ref (must be dict): {ref}")
                if "number" not in ref:
                    raise ToolError(f"Missing 'number' in PR ref: {ref}")
                if "owner" not in ref or "repo" not in ref:
                    raise ToolError(
                        f"Missing 'owner' or 'repo' in PR ref: {ref}. "
                        "Each ref must have owner, repo, and number."
                    )
                validated_refs.append(
                    {
                        "owner": ref["owner"],
                        "repo": ref["repo"],
                        "number": int(ref["number"]),
                    }
                )

            if not validated_refs:
                return {"count": 0, "prs": []}

            # Fetch all PRs in parallel
            prs = client.fetch_prs_parallel(validated_refs, max_workers=10)

            return {
                "count": len(prs),
                "requested": len(validated_refs),
                "prs": prs,
            }
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to fetch PRs: {str(e)}")

    @mcp.tool(tags={"github", "commits"})
    def list_commits(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        branch: Optional[str] = Field(
            default=None,
            description="Branch name to list commits from. Defaults to default branch.",
        ),
        author: Optional[str] = Field(
            default=None,
            description="Filter by author username",
        ),
        since: Optional[str] = Field(
            default=None,
            description="ISO datetime - only commits after this date (e.g., '2024-01-01T00:00:00Z')",
        ),
        limit: int = Field(
            default=20,
            description="Maximum number of commits to return (default: 20)",
        ),
        detail_level: str = Field(
            default="summary",
            description="'summary' for minimal fields (short sha, message title, author, date, url), "
            "'full' for all fields including full commit message. Use 'summary' for large result sets.",
        ),
    ) -> dict:
        """
        List commits for a GitHub repository.

        Returns commits sorted by date (newest first).
        Use detail_level='summary' (default) to avoid context overflow.
        Use get_commit(sha) for full details on a specific commit.
        """
        try:
            client = _get_client()
            commits = client.list_commits(
                owner=owner,
                repo=repo,
                sha=branch,
                author=author,
                since=since,
                limit=limit,
                detail_level=detail_level,
            )

            return {
                "count": len(commits),
                "detail_level": detail_level,
                "commits": [commit.model_dump() for commit in commits],
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list commits: {str(e)}")

    @mcp.tool(tags={"github", "commits"})
    def get_commit(
        sha: str = Field(..., description="Commit SHA (full or abbreviated)"),
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
    ) -> dict:
        """
        Get detailed information about a specific commit.

        Includes commit message, author, stats, and file changes.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            commit = client.get_commit(sha, owner=owner, repo=repo)

            if not commit:
                raise ToolError(f"Commit {sha} not found")

            return {"commit": commit}
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to get commit {sha}: {str(e)}")

    @mcp.tool(tags={"github", "branches"})
    def list_branches(
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner. Uses your GitHub username if not specified.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
        limit: int = Field(
            default=30,
            description="Maximum number of branches to return (default: 30)",
        ),
    ) -> dict:
        """
        List branches for a GitHub repository.

        Returns branch names with their latest commit SHA and protection status.
        Requires QuickCall authentication with GitHub connected.
        """
        try:
            client = _get_client()
            branches = client.list_branches(owner=owner, repo=repo, limit=limit)

            return {
                "count": len(branches),
                "branches": branches,
            }
        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(
                f"Repository not specified: {str(e)}. "
                f"Please provide both owner and repo parameters."
            )
        except Exception as e:
            raise ToolError(f"Failed to list branches: {str(e)}")

    @mcp.tool(tags={"github", "issues"})
    def manage_issues(
        action: str = Field(
            ...,
            description="Action: 'create', 'update', 'close', 'reopen', or 'comment'",
        ),
        issue_numbers: Optional[List[int]] = Field(
            default=None,
            description="Issue number(s). Required for update/close/reopen/comment. Supports bulk operations.",
        ),
        title: Optional[str] = Field(
            default=None,
            description="Issue title (for 'create' or 'update')",
        ),
        body: Optional[str] = Field(
            default=None,
            description="Issue body (for 'create'/'update') or comment text (for 'comment')",
        ),
        labels: Optional[List[str]] = Field(
            default=None,
            description="Labels (for 'create' or 'update')",
        ),
        assignees: Optional[List[str]] = Field(
            default=None,
            description="GitHub usernames to assign",
        ),
        template: Optional[str] = Field(
            default=None,
            description="Template name for 'create' (e.g., 'bug', 'feature')",
        ),
        owner: Optional[str] = Field(
            default=None,
            description="Repository owner",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Repository name. Required.",
        ),
    ) -> dict:
        """
        Manage GitHub issues: create, update, close, reopen, or comment.

        Supports bulk operations for close/reopen/comment via issue_numbers list.

        Examples:
        - create: manage_issues(action="create", title="Bug", template="bug")
        - close multiple: manage_issues(action="close", issue_numbers=[1, 2, 3])
        - comment: manage_issues(action="comment", issue_numbers=[42], body="Fixed!")
        """
        try:
            client = _get_client()

            if action == "create":
                if not title:
                    raise ToolError("'title' is required for 'create' action")

                tpl = _load_issue_template(template)
                final_body = body if body is not None else tpl.get("body", "")
                final_labels = labels if labels is not None else tpl.get("labels", [])

                issue = client.create_issue(
                    title=title,
                    body=final_body,
                    labels=final_labels,
                    assignees=assignees,
                    owner=owner,
                    repo=repo,
                )
                return {"action": "created", "issue": issue}

            # All other actions require issue_numbers
            if not issue_numbers:
                raise ToolError(f"'issue_numbers' required for '{action}' action")

            results = []
            for issue_number in issue_numbers:
                if action == "update":
                    client.update_issue(
                        issue_number=issue_number,
                        title=title,
                        body=body,
                        labels=labels,
                        assignees=assignees,
                        owner=owner,
                        repo=repo,
                    )
                    results.append({"number": issue_number, "status": "updated"})

                elif action == "close":
                    client.close_issue(issue_number, owner=owner, repo=repo)
                    results.append({"number": issue_number, "status": "closed"})

                elif action == "reopen":
                    client.reopen_issue(issue_number, owner=owner, repo=repo)
                    results.append({"number": issue_number, "status": "reopened"})

                elif action == "comment":
                    if not body:
                        raise ToolError("'body' is required for 'comment' action")
                    comment = client.comment_on_issue(
                        issue_number, body=body, owner=owner, repo=repo
                    )
                    results.append(
                        {
                            "number": issue_number,
                            "status": "commented",
                            "comment_url": comment["html_url"],
                        }
                    )

                else:
                    raise ToolError(f"Invalid action: {action}")

            return {"action": action, "count": len(results), "results": results}

        except ToolError:
            raise
        except ValueError as e:
            raise ToolError(f"Repository not specified: {str(e)}")
        except Exception as e:
            raise ToolError(f"Failed to {action} issue(s): {str(e)}")

    @mcp.tool(tags={"github", "prs", "appraisal"})
    def prepare_appraisal_data(
        author: Optional[str] = Field(
            default=None,
            description="GitHub username. Defaults to authenticated user.",
        ),
        days: int = Field(
            default=180,
            description="Number of days to look back (default: 180 for ~6 months)",
        ),
        org: Optional[str] = Field(
            default=None,
            description="GitHub org to search within.",
        ),
        repo: Optional[str] = Field(
            default=None,
            description="Specific repo in 'owner/repo' format.",
        ),
    ) -> dict:
        """
        Fetch all merged PRs for appraisals/performance reviews.

        Returns:
        - file_path: temp file with full PR data (additions, deletions, files)
        - pr_titles: list of {number, title, repo} for Claude to review
        - count: total PRs found

        Workflow:
        1. Call this tool → get file_path and pr_titles
        2. Review pr_titles, pick significant PRs
        3. Call get_appraisal_pr_details(file_path, [pr_numbers]) for full details
        """
        import json
        import tempfile
        from datetime import datetime, timedelta, timezone

        try:
            client = _get_client()

            since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
                "%Y-%m-%d"
            )

            # Use authenticated user if author not specified
            if not author:
                creds = get_credential_store().get_api_credentials()
                if creds and creds.github_username:
                    author = creds.github_username

            # Step 1: Get list of merged PRs
            pr_list = client.search_merged_prs(
                author=author,
                since_date=since_date,
                org=org,
                repo=repo,
                limit=100,
                detail_level="full",  # Get body/labels from search
            )

            if not pr_list:
                return {
                    "count": 0,
                    "message": "No merged PRs found for the specified criteria",
                    "author": author,
                    "period": f"Last {days} days",
                }

            # Step 2: Prepare refs for parallel fetch
            pr_refs = [
                {"owner": pr["owner"], "repo": pr["repo"], "number": pr["number"]}
                for pr in pr_list
            ]

            # Step 3: Fetch full details in parallel
            full_prs = client.fetch_prs_parallel(pr_refs, max_workers=10)

            # Step 4: Merge search data with full PR data
            # (search has body/labels, full PR has additions/deletions/files)
            pr_lookup = {(pr["owner"], pr["repo"], pr["number"]): pr for pr in pr_list}
            for pr in full_prs:
                key = (pr["owner"], pr["repo"], pr["number"])
                if key in pr_lookup:
                    # Add labels from search (not in PyGithub response for some reason)
                    search_pr = pr_lookup[key]
                    if "labels" in search_pr:
                        pr["labels"] = search_pr["labels"]

            # Step 5: Dump to file
            dump_data = {
                "author": author,
                "period": f"Last {days} days",
                "org": org,
                "repo": repo,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": len(full_prs),
                "prs": full_prs,
            }

            # Create temp file that persists
            fd, file_path = tempfile.mkstemp(suffix=".json", prefix="appraisal_")
            with open(file_path, "w") as f:
                json.dump(dump_data, f, indent=2, default=str)

            # Step 6: Return file path + just titles for Claude to scan
            pr_titles = [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "repo": f"{pr['owner']}/{pr['repo']}",
                }
                for pr in full_prs
            ]

            return {
                "file_path": file_path,
                "count": len(full_prs),
                "author": author,
                "period": f"Last {days} days",
                "pr_titles": pr_titles,
                "next_step": "Review titles above, then call "
                "get_appraisal_pr_details(file_path, pr_numbers) for full details on selected PRs.",
            }

        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to prepare appraisal data: {str(e)}")

    @mcp.tool(tags={"github", "prs", "appraisal"})
    def get_appraisal_pr_details(
        file_path: str = Field(
            ...,
            description="Path to the appraisal data file from prepare_appraisal_data",
        ),
        pr_numbers: List[int] = Field(
            ..., description="List of PR numbers to get full details for"
        ),
    ) -> dict:
        """
        Read full PR details from the appraisal data file.

        Call this after prepare_appraisal_data with selected PR numbers.
        Reads from the cached file - no API calls made.

        Returns: additions, deletions, files changed, body for selected PRs.
        """
        import json

        try:
            with open(file_path) as f:
                data = json.load(f)

            pr_numbers_set = set(pr_numbers)
            selected_prs = [
                pr for pr in data.get("prs", []) if pr["number"] in pr_numbers_set
            ]

            return {
                "count": len(selected_prs),
                "requested": len(pr_numbers),
                "prs": selected_prs,
            }

        except FileNotFoundError:
            raise ToolError(f"Appraisal data file not found: {file_path}")
        except json.JSONDecodeError:
            raise ToolError(f"Invalid JSON in appraisal data file: {file_path}")
        except Exception as e:
            raise ToolError(f"Failed to read appraisal data: {str(e)}")

    @mcp.tool(tags={"github", "status"})
    def check_github_connection() -> dict:
        """
        Check if GitHub is connected and working.

        Tests the GitHub connection by fetching your account info.
        Shows whether using QuickCall GitHub App or PAT fallback.
        Use this to verify your GitHub integration is working.
        """
        store = get_credential_store()

        # First, try to get a working client (this handles both QuickCall and PAT)
        try:
            client = _get_client()
            using_pat, pat_source = is_using_pat_mode()

            # Try to get username to verify connection works
            try:
                username = client.get_authenticated_user()
            except Exception:
                username = None

            if using_pat:
                return {
                    "connected": True,
                    "mode": "pat",
                    "pat_source": pat_source,
                    "username": username or get_github_pat_username(),
                    "note": "Using Personal Access Token (PAT) mode. "
                    "Some features like list_repos may have limited access.",
                }
            else:
                creds = store.get_api_credentials()
                return {
                    "connected": True,
                    "mode": "github_app",
                    "username": username or (creds.github_username if creds else None),
                    "installation_id": creds.github_installation_id if creds else None,
                }
        except ToolError as e:
            # No authentication available
            pat_token, _ = get_github_pat()
            if pat_token:
                # PAT exists but failed to work
                return {
                    "connected": False,
                    "error": "PAT authentication failed. Token may be invalid or expired.",
                    "suggestion": "Check your GITHUB_TOKEN or .quickcall.env file.",
                }

            # Check QuickCall status for helpful error
            if store.is_authenticated():
                creds = store.get_api_credentials()
                if creds and not creds.github_connected:
                    return {
                        "connected": False,
                        "error": "GitHub not connected via QuickCall.",
                        "suggestions": [
                            "Connect GitHub App at quickcall.dev/assistant",
                            "Or set GITHUB_TOKEN environment variable",
                            "Or create .quickcall.env with GITHUB_TOKEN=ghp_xxx",
                        ],
                    }

            return {
                "connected": False,
                "error": str(e),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
