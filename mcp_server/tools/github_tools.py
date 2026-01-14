"""
GitHub Tools - Pull requests and commits via GitHub API.

Authentication (in priority order):
1. QuickCall GitHub App (preferred) - connect via connect_quickcall
2. Personal Access Token (PAT) - set GITHUB_TOKEN env var or use .quickcall.env file

PAT fallback is useful for:
- Users at organizations that can't install the GitHub App
- Personal repositories without app installation
- Testing and development
"""

from typing import List, Optional, Tuple
import logging

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.auth import (
    get_credential_store,
    get_github_pat,
    get_github_pat_username,
)
from mcp_server.api_clients.github_client import GitHubClient

logger = logging.getLogger(__name__)


# Track whether we're using PAT mode for status reporting
_using_pat_mode: bool = False
_pat_source: Optional[str] = None


def _get_client() -> GitHubClient:
    """
    Get the GitHub client using the best available authentication method.

    Authentication priority:
    1. QuickCall GitHub App (if connected and working)
    2. Personal Access Token from environment/config file

    Raises:
        ToolError: If no authentication method is available
    """
    global _using_pat_mode, _pat_source

    store = get_credential_store()

    # Try QuickCall GitHub App first (preferred)
    if store.is_authenticated():
        creds = store.get_api_credentials()
        if creds and creds.github_connected and creds.github_token:
            _using_pat_mode = False
            _pat_source = None
            return GitHubClient(
                token=creds.github_token,
                default_owner=creds.github_username,
                installation_id=creds.github_installation_id,
            )

    # Try PAT fallback
    pat_token, pat_source = get_github_pat()
    if pat_token:
        _using_pat_mode = True
        _pat_source = pat_source
        pat_username = get_github_pat_username()
        logger.info(f"Using GitHub PAT from {pat_source}")
        return GitHubClient(
            token=pat_token,
            default_owner=pat_username,
            installation_id=None,  # No installation ID for PAT
        )

    # No authentication available - provide helpful error message
    _using_pat_mode = False
    _pat_source = None

    if store.is_authenticated():
        # Connected to QuickCall but GitHub not connected
        raise ToolError(
            "GitHub not connected. Options:\n"
            "1. Connect GitHub App at quickcall.dev/assistant (recommended)\n"
            "2. Run connect_github_via_pat with your Personal Access Token\n"
            "3. Set GITHUB_TOKEN environment variable"
        )
    else:
        # Not connected to QuickCall at all
        raise ToolError(
            "GitHub authentication required. Options:\n"
            "1. Run connect_quickcall to use QuickCall (full access to GitHub + Slack)\n"
            "2. Run connect_github_via_pat with a Personal Access Token (GitHub only)\n"
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
