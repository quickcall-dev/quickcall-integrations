"""
GitHub API client for MCP server.

Provides GitHub API operations using PyGithub library.
Focuses on PRs and commits for minimal implementation.
"""

import logging
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
    """Represents a GitHub commit."""

    sha: str
    message: str
    author: str
    date: datetime
    html_url: str


class PullRequest(BaseModel):
    """Represents a GitHub pull request."""

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
            token: GitHub installation access token
            default_owner: Default repository owner (optional)
            default_repo: Default repository name (optional)
            installation_id: GitHub App installation ID (for listing repos)
        """
        self.token = token
        self.default_owner = default_owner
        self.default_repo = default_repo
        self.installation_id = installation_id

        # Initialize PyGithub client
        auth = Auth.Token(token)
        self.gh = Github(auth=auth)

        # Cache for repo objects
        self._repo_cache: Dict[str, Any] = {}

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
            # Use installation/repositories endpoint - works with GitHub App tokens
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
        Get the GitHub username associated with this installation.

        Note: GitHub App installation tokens can't access /user endpoint.
        We return the installation owner instead.
        """
        # Try to get from first repo's owner
        try:
            repos = self.list_repos(limit=1)
            if repos:
                return repos[0].owner.login
        except Exception:
            pass
        return "GitHub App"  # Fallback

    def close(self):
        """Close GitHub API client."""
        self.gh.close()

    # ========================================================================
    # Repository Operations
    # ========================================================================

    def list_repos(self, limit: int = 20) -> List[Repository]:
        """
        List repositories accessible to the GitHub App installation.

        Args:
            limit: Maximum repositories to return

        Returns:
            List of repositories
        """
        repos = []
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
    ) -> List[PullRequest]:
        """
        List pull requests.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state: 'open', 'closed', or 'all'
            limit: Maximum PRs to return

        Returns:
            List of pull requests
        """
        gh_repo = self._get_repo(owner, repo)
        prs = []

        for pr in gh_repo.get_pulls(state=state, sort="updated", direction="desc")[
            :limit
        ]:
            prs.append(self._convert_pr(pr))

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
        """Convert PyGithub PullRequest to Pydantic model."""
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
    ) -> List[Commit]:
        """
        List commits.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Branch name or commit SHA to start from
            author: Filter by author username
            since: ISO datetime - only commits after this date
            limit: Maximum commits to return

        Returns:
            List of commits
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

            commits.append(
                Commit(
                    sha=commit.sha,
                    message=commit.commit.message,
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
