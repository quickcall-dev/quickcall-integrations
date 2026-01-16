"""
GitHub API client for MCP server.

Provides GitHub API operations using PyGithub library.
Focuses on PRs and commits for minimal implementation.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any
from datetime import datetime

from github import Github, GithubException, Auth
from pydantic import BaseModel
import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic models for GitHub data
# ============================================================================


class Commit(BaseModel):
    """Represents a GitHub commit (full details)."""

    sha: str
    message: str
    author: str
    date: datetime
    html_url: str


class CommitSummary(BaseModel):
    """Represents a GitHub commit (summary - minimal fields for list operations)."""

    sha: str
    message_title: str  # First line only
    author: str
    date: datetime
    html_url: str


class PullRequest(BaseModel):
    """Represents a GitHub pull request (full details)."""

    number: int
    title: str
    body: Optional[str] = None
    state: str  # open, closed
    author: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    html_url: str
    head_branch: str
    base_branch: str
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    commits: int = 0
    draft: bool = False
    mergeable: Optional[bool] = None
    labels: List[str] = []
    reviewers: List[str] = []


class PullRequestSummary(BaseModel):
    """Represents a GitHub pull request (summary - minimal fields for list operations)."""

    number: int
    title: str
    state: str
    author: str
    created_at: datetime
    merged_at: Optional[datetime] = None
    html_url: str


class Repository(BaseModel):
    """Represents a GitHub repository."""

    name: str
    owner: str
    full_name: str
    html_url: str
    description: str = ""
    default_branch: str
    private: bool = False


# ============================================================================
# GitHub Client
# ============================================================================


class GitHubClient:
    """
    GitHub API client using PyGithub.

    Provides simplified interface for GitHub operations.
    Focuses on PRs and commits.

    Supports both:
    - GitHub App installation tokens (via QuickCall)
    - Personal Access Tokens (PAT fallback)
    """

    def __init__(
        self,
        token: str,
        default_owner: Optional[str] = None,
        default_repo: Optional[str] = None,
        installation_id: Optional[int] = None,
    ):
        """
        Initialize GitHub API client.

        Args:
            token: GitHub access token (installation token or PAT)
            default_owner: Default repository owner (optional)
            default_repo: Default repository name (optional)
            installation_id: GitHub App installation ID (None for PAT mode)
        """
        self.token = token
        self.default_owner = default_owner
        self.default_repo = default_repo
        self.installation_id = installation_id

        # Detect if this is a PAT (no installation_id means PAT mode)
        self._is_pat_mode = installation_id is None

        # Initialize PyGithub client
        auth = Auth.Token(token)
        self.gh = Github(auth=auth)

        # Cache for repo objects
        self._repo_cache: Dict[str, Any] = {}

    @property
    def is_pat_mode(self) -> bool:
        """Check if client is using PAT authentication."""
        return self._is_pat_mode

    def _get_repo(self, owner: Optional[str] = None, repo: Optional[str] = None):
        """Get PyGithub repo object, using defaults if not specified."""
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError(
                "Repository owner and name must be specified or set as defaults"
            )

        full_name = f"{owner}/{repo}"
        if full_name not in self._repo_cache:
            self._repo_cache[full_name] = self.gh.get_repo(full_name)

        return self._repo_cache[full_name]

    def health_check(self) -> bool:
        """Check if GitHub API is accessible with the token."""
        try:
            if self._is_pat_mode:
                # For PAT, use /user endpoint
                user = self.gh.get_user()
                _ = user.login  # This will trigger the API call
                return True
            else:
                # For installation tokens, use /installation/repositories endpoint
                with httpx.Client() as client:
                    response = client.get(
                        "https://api.github.com/installation/repositories",
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28",
                        },
                        params={"per_page": 1},
                    )
                    return response.status_code == 200
        except Exception:
            return False

    def get_authenticated_user(self) -> str:
        """
        Get the GitHub username for the authenticated user/installation.

        For PAT: Returns the user's login
        For GitHub App: Returns the installation owner
        """
        if self._is_pat_mode:
            try:
                user = self.gh.get_user()
                return user.login
            except Exception:
                return self.default_owner or "unknown"
        else:
            # GitHub App installation tokens can't access /user endpoint
            # Try to get from first repo's owner
            try:
                repos = self.list_repos(limit=1)
                if repos:
                    return repos[0].owner
            except Exception:
                pass
            return self.default_owner or "GitHub App"

    def close(self):
        """Close GitHub API client."""
        self.gh.close()

    # ========================================================================
    # Repository Operations
    # ========================================================================

    def list_repos(self, limit: int = 20) -> List[Repository]:
        """
        List repositories accessible to the authenticated user/installation.

        For PAT mode: Lists user's repositories
        For GitHub App: Lists installation repositories

        Args:
            limit: Maximum repositories to return

        Returns:
            List of repositories
        """
        repos = []

        if self._is_pat_mode:
            # PAT mode: Use PyGithub's user.get_repos()
            try:
                user = self.gh.get_user()
                for i, gh_repo in enumerate(user.get_repos(sort="updated")):
                    if i >= limit:
                        break
                    repos.append(
                        Repository(
                            name=gh_repo.name,
                            owner=gh_repo.owner.login,
                            full_name=gh_repo.full_name,
                            html_url=gh_repo.html_url,
                            description=gh_repo.description or "",
                            default_branch=gh_repo.default_branch,
                            private=gh_repo.private,
                        )
                    )
            except GithubException as e:
                logger.error(f"Failed to list user repos: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to list user repos: {e}")
                raise
        else:
            # GitHub App mode: Use /installation/repositories endpoint
            try:
                # Installation tokens can't use PyGithub's user.get_repos() endpoint
                # Must use /installation/repositories endpoint directly (same as backend)
                # https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation
                with httpx.Client() as client:
                    response = client.get(
                        "https://api.github.com/installation/repositories",
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28",
                        },
                        params={"per_page": limit},
                    )
                    response.raise_for_status()
                    data = response.json()

                    for repo_data in data.get("repositories", [])[:limit]:
                        repos.append(
                            Repository(
                                name=repo_data["name"],
                                owner=repo_data["owner"]["login"],
                                full_name=repo_data["full_name"],
                                html_url=repo_data["html_url"],
                                description=repo_data.get("description") or "",
                                default_branch=repo_data.get("default_branch", "main"),
                                private=repo_data.get("private", False),
                            )
                        )
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Failed to list installation repos: HTTP {e.response.status_code}"
                )
                raise GithubException(e.response.status_code, e.response.json())
            except Exception as e:
                logger.error(f"Failed to list installation repos: {e}")
                raise

        return repos

    def get_repo_info(
        self, owner: Optional[str] = None, repo: Optional[str] = None
    ) -> Repository:
        """Get repository information."""
        gh_repo = self._get_repo(owner, repo)
        return Repository(
            name=gh_repo.name,
            owner=gh_repo.owner.login,
            full_name=gh_repo.full_name,
            html_url=gh_repo.html_url,
            description=gh_repo.description or "",
            default_branch=gh_repo.default_branch,
            private=gh_repo.private,
        )

    # ========================================================================
    # Pull Request Operations
    # ========================================================================

    def list_prs(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        state: str = "open",
        limit: int = 20,
        detail_level: str = "summary",
    ) -> List[PullRequest] | List[PullRequestSummary]:
        """
        List pull requests.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state: 'open', 'closed', or 'all'
            limit: Maximum PRs to return
            detail_level: 'summary' for minimal fields (~200 bytes/PR),
                         'full' for all fields (~2KB/PR)

        Returns:
            List of pull requests (summary or full based on detail_level)
        """
        gh_repo = self._get_repo(owner, repo)
        prs = []

        try:
            pulls = gh_repo.get_pulls(state=state, sort="updated", direction="desc")
            for i, pr in enumerate(pulls):
                if i >= limit:
                    break
                if detail_level == "full":
                    prs.append(self._convert_pr(pr))
                else:
                    prs.append(self._convert_pr_summary(pr))
        except IndexError:
            # Empty repo or no PRs - return empty list
            pass

        return prs

    def get_pr(
        self,
        pr_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Optional[PullRequest]:
        """
        Get a specific pull request by number.

        Args:
            pr_number: PR number
            owner: Repository owner
            repo: Repository name

        Returns:
            PullRequest or None if not found
        """
        try:
            gh_repo = self._get_repo(owner, repo)
            pr = gh_repo.get_pull(pr_number)
            return self._convert_pr(pr)
        except GithubException as e:
            if e.status == 404:
                return None
            raise

    def _convert_pr(self, pr) -> PullRequest:
        """Convert PyGithub PullRequest to Pydantic model (full details)."""
        return PullRequest(
            number=pr.number,
            title=pr.title,
            body=pr.body,
            state=pr.state,
            author=pr.user.login if pr.user else "unknown",
            created_at=pr.created_at,
            updated_at=pr.updated_at,
            merged_at=pr.merged_at,
            html_url=pr.html_url,
            head_branch=pr.head.ref,
            base_branch=pr.base.ref,
            additions=pr.additions,
            deletions=pr.deletions,
            changed_files=pr.changed_files,
            commits=pr.commits,
            draft=pr.draft,
            mergeable=pr.mergeable,
            labels=[label.name for label in pr.labels],
            reviewers=[r.login for r in pr.requested_reviewers],
        )

    def _convert_pr_summary(self, pr) -> PullRequestSummary:
        """Convert PyGithub PullRequest to summary model (minimal fields)."""
        return PullRequestSummary(
            number=pr.number,
            title=pr.title,
            state=pr.state,
            author=pr.user.login if pr.user else "unknown",
            created_at=pr.created_at,
            merged_at=pr.merged_at,
            html_url=pr.html_url,
        )

    # ========================================================================
    # Commit Operations
    # ========================================================================

    def list_commits(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        sha: Optional[str] = None,
        author: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 20,
        detail_level: str = "summary",
    ) -> List[Commit] | List[CommitSummary]:
        """
        List commits.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Branch name or commit SHA to start from
            author: Filter by author username
            since: ISO datetime - only commits after this date
            limit: Maximum commits to return
            detail_level: 'summary' for minimal fields, 'full' for all fields

        Returns:
            List of commits (summary or full based on detail_level)
        """
        gh_repo = self._get_repo(owner, repo)

        kwargs = {}
        if sha:
            kwargs["sha"] = sha
        if since:
            kwargs["since"] = datetime.fromisoformat(since.replace("Z", "+00:00"))

        commits = []
        for commit in gh_repo.get_commits(**kwargs):
            if len(commits) >= limit:
                break

            # Get author login
            commit_author = "unknown"
            if commit.author:
                commit_author = commit.author.login
            elif commit.commit.author:
                commit_author = commit.commit.author.name

            # Apply author filter
            if author and author.lower() != commit_author.lower():
                continue

            if detail_level == "full":
                commits.append(
                    Commit(
                        sha=commit.sha,
                        message=commit.commit.message,
                        author=commit_author,
                        date=commit.commit.author.date,
                        html_url=commit.html_url,
                    )
                )
            else:
                # Summary: just first line of message
                message_title = commit.commit.message.split("\n")[0][:100]
                commits.append(
                    CommitSummary(
                        sha=commit.sha[:7],  # Short SHA for summary
                        message_title=message_title,
                        author=commit_author,
                        date=commit.commit.author.date,
                        html_url=commit.html_url,
                    )
                )

        return commits

    def get_commit(
        self,
        sha: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed commit information including file changes.

        Args:
            sha: Commit SHA
            owner: Repository owner
            repo: Repository name

        Returns:
            Commit details with files or None if not found
        """
        try:
            gh_repo = self._get_repo(owner, repo)
            commit = gh_repo.get_commit(sha)

            return {
                "sha": commit.sha,
                "message": commit.commit.message,
                "author": commit.author.login if commit.author else "unknown",
                "date": commit.commit.author.date.isoformat(),
                "html_url": commit.html_url,
                "stats": {
                    "additions": commit.stats.additions,
                    "deletions": commit.stats.deletions,
                    "total": commit.stats.total,
                },
                "files": [
                    {
                        "filename": f.filename,
                        "status": f.status,
                        "additions": f.additions,
                        "deletions": f.deletions,
                        "patch": f.patch[:1000] if f.patch else None,
                    }
                    for f in commit.files[:30]  # Limit files
                ],
            }
        except GithubException as e:
            if e.status == 404:
                return None
            raise

    # ========================================================================
    # Branch Operations
    # ========================================================================

    def list_branches(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        List repository branches.

        Args:
            owner: Repository owner
            repo: Repository name
            limit: Maximum branches to return

        Returns:
            List of branch info dicts
        """
        gh_repo = self._get_repo(owner, repo)
        branches = []

        for branch in gh_repo.get_branches()[:limit]:
            branches.append(
                {
                    "name": branch.name,
                    "sha": branch.commit.sha,
                    "protected": branch.protected,
                }
            )

        return branches

    # ========================================================================
    # Issue Operations
    # ========================================================================

    def _issue_to_dict(self, issue) -> Dict[str, Any]:
        """Convert PyGithub Issue to dict."""
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "html_url": issue.html_url,
            "labels": [label.name for label in issue.labels],
            "assignees": [a.login for a in issue.assignees],
            "created_at": issue.created_at.isoformat(),
        }

    def create_issue(
        self,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a GitHub issue."""
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.create_issue(
            title=title,
            body=body or "",
            labels=labels or [],
            assignees=assignees or [],
        )
        return self._issue_to_dict(issue)

    def update_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a GitHub issue."""
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)

        kwargs = {}
        if title is not None:
            kwargs["title"] = title
        if body is not None:
            kwargs["body"] = body
        if labels is not None:
            kwargs["labels"] = labels
        if assignees is not None:
            kwargs["assignees"] = assignees

        if kwargs:
            issue.edit(**kwargs)

        return self._issue_to_dict(issue)

    def close_issue(
        self,
        issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close a GitHub issue."""
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)
        issue.edit(state="closed")
        return self._issue_to_dict(issue)

    def reopen_issue(
        self,
        issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reopen a GitHub issue."""
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)
        issue.edit(state="open")
        return self._issue_to_dict(issue)

    def comment_on_issue(
        self,
        issue_number: int,
        body: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a comment to a GitHub issue."""
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)
        comment = issue.create_comment(body)
        return {
            "id": comment.id,
            "body": comment.body,
            "html_url": comment.html_url,
            "created_at": comment.created_at.isoformat(),
            "issue_number": issue_number,
        }

    # ========================================================================
    # Search Operations (for Appraisals)
    # ========================================================================

    def search_merged_prs(
        self,
        author: Optional[str] = None,
        since_date: Optional[str] = None,
        org: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 100,
        detail_level: str = "summary",
    ) -> List[Dict[str, Any]]:
        """
        Search for merged pull requests using GitHub Search API.

        Ideal for gathering contribution data for appraisals/reviews.

        Args:
            author: GitHub username to filter by
            since_date: ISO date string (YYYY-MM-DD) - only PRs merged after this date
            org: GitHub org to search within
            repo: Specific repo in "owner/repo" format (overrides org if specified)
            limit: Maximum PRs to return (max 100 per page)
            detail_level: 'summary' for minimal fields, 'full' for all fields

        Returns:
            List of merged PR dicts. Summary includes: number, title, merged_at,
            repo, owner, html_url, author. Full adds: body, labels.
        """
        # Build search query
        query_parts = ["is:pr", "is:merged"]

        if author:
            query_parts.append(f"author:{author}")

        if since_date:
            query_parts.append(f"merged:>={since_date}")

        # repo takes precedence over org
        if repo:
            query_parts.append(f"repo:{repo}")
        elif org:
            query_parts.append(f"org:{org}")

        query = " ".join(query_parts)

        try:
            with httpx.Client() as client:
                response = client.get(
                    "https://api.github.com/search/issues",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    params={
                        "q": query,
                        "sort": "updated",
                        "order": "desc",
                        "per_page": min(limit, 100),
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            # Convert to simplified format
            prs = []
            for item in data.get("items", [])[:limit]:
                # Extract repo info from repository_url
                # Format: https://api.github.com/repos/owner/repo
                repo_url_parts = item.get("repository_url", "").split("/")
                repo_owner = repo_url_parts[-2] if len(repo_url_parts) >= 2 else ""
                repo_name = repo_url_parts[-1] if len(repo_url_parts) >= 1 else ""

                if detail_level == "full":
                    prs.append(
                        {
                            "number": item["number"],
                            "title": item["title"],
                            "body": item.get("body") or "",
                            "merged_at": item.get("pull_request", {}).get("merged_at"),
                            "html_url": item["html_url"],
                            "labels": [
                                label["name"] for label in item.get("labels", [])
                            ],
                            "repo": repo_name,
                            "owner": repo_owner,
                            "author": item.get("user", {}).get("login", "unknown"),
                        }
                    )
                else:
                    # Summary: skip body and labels
                    prs.append(
                        {
                            "number": item["number"],
                            "title": item["title"],
                            "merged_at": item.get("pull_request", {}).get("merged_at"),
                            "html_url": item["html_url"],
                            "repo": repo_name,
                            "owner": repo_owner,
                            "author": item.get("user", {}).get("login", "unknown"),
                        }
                    )

            return prs

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to search PRs: HTTP {e.response.status_code}")
            raise GithubException(e.response.status_code, e.response.json())
        except Exception as e:
            logger.error(f"Failed to search PRs: {e}")
            raise

    def fetch_prs_parallel(
        self,
        pr_refs: List[Dict[str, Any]],
        max_workers: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch full PR details for multiple PRs in parallel.

        Args:
            pr_refs: List of dicts with 'owner', 'repo', 'number' keys
            max_workers: Max concurrent requests (default: 10)

        Returns:
            List of full PR details with stats (additions, deletions, files)
        """
        results = []
        errors = []

        def fetch_single_pr(pr_ref: Dict[str, Any]) -> Dict[str, Any] | None:
            try:
                owner = pr_ref["owner"]
                repo = pr_ref["repo"]
                number = pr_ref["number"]
                pr = self.get_pr(number, owner=owner, repo=repo)
                if pr:
                    pr_dict = pr.model_dump()
                    # Add owner/repo for context
                    pr_dict["owner"] = owner
                    pr_dict["repo"] = repo
                    return pr_dict
                return None
            except Exception as e:
                logger.warning(f"Failed to fetch PR {pr_ref}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_single_pr, pr_ref): pr_ref for pr_ref in pr_refs
            }

            for future in as_completed(futures):
                pr_ref = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                    else:
                        errors.append(pr_ref)
                except Exception as e:
                    logger.error(f"Error fetching {pr_ref}: {e}")
                    errors.append(pr_ref)

        if errors:
            logger.warning(f"Failed to fetch {len(errors)} PRs: {errors[:5]}...")

        return results
