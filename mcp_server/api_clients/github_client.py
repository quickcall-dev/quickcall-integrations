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

    def create_pr(
        self,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        draft: bool = False,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> PullRequest:
        """
        Create a new pull request.

        Args:
            title: PR title
            head: Branch containing changes (e.g., "feature-branch")
            base: Branch to merge into (e.g., "main")
            body: PR description
            draft: Create as draft PR
            owner: Repository owner
            repo: Repository name

        Returns:
            Created PullRequest
        """
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.create_pull(
            title=title,
            head=head,
            base=base,
            body=body or "",
            draft=draft,
        )
        return self._convert_pr(pr)

    def update_pr(
        self,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        base: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> PullRequest:
        """
        Update an existing pull request.

        Args:
            pr_number: PR number
            title: New title
            body: New description
            state: New state ('open' or 'closed')
            base: New base branch
            owner: Repository owner
            repo: Repository name

        Returns:
            Updated PullRequest
        """
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)

        kwargs = {}
        if title is not None:
            kwargs["title"] = title
        if body is not None:
            kwargs["body"] = body
        if state is not None:
            kwargs["state"] = state
        if base is not None:
            kwargs["base"] = base

        if kwargs:
            pr.edit(**kwargs)

        return self._convert_pr(pr)

    def merge_pr(
        self,
        pr_number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Merge a pull request.

        Args:
            pr_number: PR number
            commit_title: Custom commit title (for squash/merge)
            commit_message: Custom commit message
            merge_method: 'merge', 'squash', or 'rebase'
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with merge status and SHA
        """
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)

        # Check if PR is mergeable
        if pr.merged:
            return {
                "merged": True,
                "message": "PR was already merged",
                "sha": pr.merge_commit_sha,
            }

        if not pr.mergeable:
            return {
                "merged": False,
                "message": "PR is not mergeable (conflicts or checks failing)",
                "sha": None,
            }

        # Merge the PR
        result = pr.merge(
            commit_title=commit_title,
            commit_message=commit_message,
            merge_method=merge_method,
        )

        return {
            "merged": result.merged,
            "message": result.message,
            "sha": result.sha,
        }

    def close_pr(
        self,
        pr_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> PullRequest:
        """Close a pull request without merging."""
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)
        pr.edit(state="closed")
        return self._convert_pr(pr)

    def reopen_pr(
        self,
        pr_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> PullRequest:
        """Reopen a closed pull request."""
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)
        pr.edit(state="open")
        return self._convert_pr(pr)

    def add_pr_comment(
        self,
        pr_number: int,
        body: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a comment to a pull request.

        Args:
            pr_number: PR number
            body: Comment text
            owner: Repository owner
            repo: Repository name

        Returns:
            Comment details
        """
        gh_repo = self._get_repo(owner, repo)
        # PRs use the issue comment API
        issue = gh_repo.get_issue(pr_number)
        comment = issue.create_comment(body)
        return {
            "id": comment.id,
            "body": comment.body,
            "html_url": comment.html_url,
            "created_at": comment.created_at.isoformat(),
            "pr_number": pr_number,
        }

    def request_reviewers(
        self,
        pr_number: int,
        reviewers: Optional[List[str]] = None,
        team_reviewers: Optional[List[str]] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Request reviewers for a pull request.

        Args:
            pr_number: PR number
            reviewers: List of GitHub usernames
            team_reviewers: List of team slugs (org teams)
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with requested reviewers
        """
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)

        # Create review request
        pr.create_review_request(
            reviewers=reviewers or [],
            team_reviewers=team_reviewers or [],
        )

        # Re-fetch to get updated reviewers
        pr = gh_repo.get_pull(pr_number)
        return {
            "pr_number": pr_number,
            "requested_reviewers": [r.login for r in pr.requested_reviewers],
            "requested_teams": [t.slug for t in pr.requested_teams],
        }

    def submit_pr_review(
        self,
        pr_number: int,
        event: str,
        body: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit a review on a pull request.

        Args:
            pr_number: PR number
            event: Review event - 'APPROVE', 'REQUEST_CHANGES', or 'COMMENT'
            body: Review comment (required for REQUEST_CHANGES)
            owner: Repository owner
            repo: Repository name

        Returns:
            Review details
        """
        gh_repo = self._get_repo(owner, repo)
        pr = gh_repo.get_pull(pr_number)

        review = pr.create_review(
            body=body or "",
            event=event,
        )

        return {
            "id": review.id,
            "state": review.state,
            "body": review.body,
            "html_url": review.html_url,
            "pr_number": pr_number,
        }

    def convert_pr_to_draft(
        self,
        pr_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert a PR to draft status using GraphQL API.

        Args:
            pr_number: PR number
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with success status
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get PR node ID
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    id
                    isDraft
                }
            }
        }
        """
        data = self._graphql_request(
            query, {"owner": owner, "repo": repo, "number": pr_number}
        )
        repository = data.get("repository")
        if not repository:
            raise GithubException(
                404, {"message": f"Repository {owner}/{repo} not found"}
            )
        pr_data = repository.get("pullRequest")
        if not pr_data:
            raise GithubException(404, {"message": f"PR #{pr_number} not found"})

        if pr_data.get("isDraft"):
            return {
                "pr_number": pr_number,
                "is_draft": True,
                "message": "PR is already a draft",
            }

        pr_node_id = pr_data["id"]

        # Convert to draft
        mutation = """
        mutation($pullRequestId: ID!) {
            convertPullRequestToDraft(input: {pullRequestId: $pullRequestId}) {
                pullRequest {
                    id
                    isDraft
                }
            }
        }
        """
        result = self._graphql_request(mutation, {"pullRequestId": pr_node_id})
        converted = result.get("convertPullRequestToDraft", {}).get("pullRequest", {})

        return {
            "pr_number": pr_number,
            "is_draft": converted.get("isDraft", True),
            "message": "PR converted to draft",
        }

    def mark_pr_ready_for_review(
        self,
        pr_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mark a draft PR as ready for review using GraphQL API.

        Args:
            pr_number: PR number
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with success status
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get PR node ID
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    id
                    isDraft
                }
            }
        }
        """
        data = self._graphql_request(
            query, {"owner": owner, "repo": repo, "number": pr_number}
        )
        repository = data.get("repository")
        if not repository:
            raise GithubException(
                404, {"message": f"Repository {owner}/{repo} not found"}
            )
        pr_data = repository.get("pullRequest")
        if not pr_data:
            raise GithubException(404, {"message": f"PR #{pr_number} not found"})

        if not pr_data.get("isDraft"):
            return {
                "pr_number": pr_number,
                "is_draft": False,
                "message": "PR is already ready for review",
            }

        pr_node_id = pr_data["id"]

        # Mark ready for review
        mutation = """
        mutation($pullRequestId: ID!) {
            markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
                pullRequest {
                    id
                    isDraft
                }
            }
        }
        """
        result = self._graphql_request(mutation, {"pullRequestId": pr_node_id})
        converted = result.get("markPullRequestReadyForReview", {}).get(
            "pullRequest", {}
        )

        return {
            "pr_number": pr_number,
            "is_draft": converted.get("isDraft", False),
            "message": "PR marked ready for review",
        }

    def add_pr_labels(
        self,
        pr_number: int,
        labels: List[str],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add labels to a pull request.

        Args:
            pr_number: PR number
            labels: List of label names
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with updated labels
        """
        gh_repo = self._get_repo(owner, repo)
        # PRs use the issue API for labels
        issue = gh_repo.get_issue(pr_number)
        issue.add_to_labels(*labels)

        return {
            "pr_number": pr_number,
            "labels": [label.name for label in issue.labels],
        }

    def remove_pr_labels(
        self,
        pr_number: int,
        labels: List[str],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove labels from a pull request.

        Args:
            pr_number: PR number
            labels: List of label names to remove
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with updated labels
        """
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(pr_number)

        for label in labels:
            try:
                issue.remove_from_labels(label)
            except GithubException as e:
                if e.status != 404:  # Ignore if label not present
                    raise

        # Re-fetch to get updated labels
        issue = gh_repo.get_issue(pr_number)
        return {
            "pr_number": pr_number,
            "labels": [label.name for label in issue.labels],
        }

    def add_pr_assignees(
        self,
        pr_number: int,
        assignees: List[str],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add assignees to a pull request.

        Args:
            pr_number: PR number
            assignees: List of GitHub usernames
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with updated assignees
        """
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(pr_number)
        issue.add_to_assignees(*assignees)

        return {
            "pr_number": pr_number,
            "assignees": [a.login for a in issue.assignees],
        }

    def remove_pr_assignees(
        self,
        pr_number: int,
        assignees: List[str],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove assignees from a pull request.

        Args:
            pr_number: PR number
            assignees: List of GitHub usernames to remove
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with updated assignees
        """
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(pr_number)

        for assignee in assignees:
            try:
                issue.remove_from_assignees(assignee)
            except GithubException as e:
                if e.status != 404:  # Ignore if not assigned
                    raise

        # Re-fetch to get updated assignees
        issue = gh_repo.get_issue(pr_number)
        return {
            "pr_number": pr_number,
            "assignees": [a.login for a in issue.assignees],
        }

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

    def _issue_to_dict(self, issue, summary: bool = False) -> Dict[str, Any]:
        """Convert PyGithub Issue to dict."""
        if summary:
            return {
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "labels": [label.name for label in issue.labels],
                "html_url": issue.html_url,
            }
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

    def list_issues(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        state: str = "open",
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        creator: Optional[str] = None,
        milestone: Optional[str] = None,
        sort: str = "updated",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        List issues in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state: 'open', 'closed', or 'all'
            labels: Filter by labels
            assignee: Filter by assignee username
            creator: Filter by issue creator username
            milestone: Filter by milestone (number, title, or '*' for any, 'none' for no milestone)
            sort: Sort by 'created', 'updated', or 'comments'
            limit: Maximum issues to return

        Returns:
            List of issue summaries
        """
        gh_repo = self._get_repo(owner, repo)

        kwargs = {"state": state, "sort": sort, "direction": "desc"}
        if labels:
            kwargs["labels"] = labels
        if assignee:
            kwargs["assignee"] = assignee
        if creator:
            kwargs["creator"] = creator
        if milestone:
            # Handle milestone - can be number, '*', 'none', or title
            if milestone == "*" or milestone == "none":
                kwargs["milestone"] = milestone
            elif milestone.isdigit():
                kwargs["milestone"] = gh_repo.get_milestone(int(milestone))
            else:
                # Search by title
                for ms in gh_repo.get_milestones(state="all"):
                    if ms.title.lower() == milestone.lower():
                        kwargs["milestone"] = ms
                        break

        issues = []
        count = 0
        for issue in gh_repo.get_issues(**kwargs):
            # Skip pull requests (GitHub API returns PRs in issues endpoint)
            if issue.pull_request is not None:
                continue
            issues.append(self._issue_to_dict(issue, summary=True))
            count += 1
            if count >= limit:
                break

        return issues

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

    def list_issue_comments(
        self,
        issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 10,
        order: str = "asc",
    ) -> List[Dict[str, Any]]:
        """
        List comments on a GitHub issue.

        Args:
            issue_number: Issue number
            owner: Repository owner
            repo: Repository name
            limit: Maximum comments to return (default: 10)
            order: 'asc' for oldest first, 'desc' for newest first (default: 'asc')

        Returns:
            List of comment dicts with id, body, author, timestamps, url
        """
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)

        comments = []
        all_comments = list(issue.get_comments())

        # Apply order
        if order == "desc":
            all_comments = all_comments[::-1]

        # Apply limit
        for comment in all_comments[:limit]:
            comments.append(
                {
                    "id": comment.id,
                    "body": comment.body,
                    "author": comment.user.login if comment.user else "unknown",
                    "created_at": comment.created_at.isoformat(),
                    "updated_at": comment.updated_at.isoformat()
                    if comment.updated_at
                    else None,
                    "html_url": comment.html_url,
                }
            )

        return comments

    def get_issue_comment(
        self,
        comment_id: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a specific comment by ID.

        Args:
            comment_id: Comment ID
            owner: Repository owner
            repo: Repository name

        Returns:
            Comment dict with id, body, author, timestamps, url
        """
        gh_repo = self._get_repo(owner, repo)
        comment = gh_repo.get_issue_comment(comment_id)

        return {
            "id": comment.id,
            "body": comment.body,
            "author": comment.user.login if comment.user else "unknown",
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat()
            if comment.updated_at
            else None,
            "html_url": comment.html_url,
        }

    def update_issue_comment(
        self,
        comment_id: int,
        body: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing comment.

        Args:
            comment_id: Comment ID
            body: New comment body
            owner: Repository owner
            repo: Repository name

        Returns:
            Updated comment dict
        """
        gh_repo = self._get_repo(owner, repo)
        comment = gh_repo.get_issue_comment(comment_id)
        comment.edit(body)

        return {
            "id": comment.id,
            "body": comment.body,
            "author": comment.user.login if comment.user else "unknown",
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat()
            if comment.updated_at
            else None,
            "html_url": comment.html_url,
        }

    def delete_issue_comment(
        self,
        comment_id: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Delete a comment.

        Args:
            comment_id: Comment ID
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with deleted comment_id
        """
        gh_repo = self._get_repo(owner, repo)
        comment = gh_repo.get_issue_comment(comment_id)
        comment.delete()

        return {
            "deleted": True,
            "comment_id": comment_id,
        }

    def get_issue(
        self,
        issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        include_sub_issues: bool = True,
    ) -> Dict[str, Any]:
        """
        Get detailed information about a GitHub issue.

        Args:
            issue_number: Issue number
            owner: Repository owner
            repo: Repository name
            include_sub_issues: Whether to fetch sub-issues list

        Returns:
            Issue details including sub-issues if requested
        """
        gh_repo = self._get_repo(owner, repo)
        issue = gh_repo.get_issue(issue_number)

        result = {
            "number": issue.number,
            "id": issue.id,  # Internal ID needed for sub-issues API
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "html_url": issue.html_url,
            "labels": [label.name for label in issue.labels],
            "assignees": [a.login for a in issue.assignees],
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            "comments_count": issue.comments,
            "author": issue.user.login if issue.user else "unknown",
        }

        # Fetch sub-issues if requested
        if include_sub_issues:
            owner = owner or self.default_owner
            repo_name = repo or self.default_repo
            sub_issues = self.list_sub_issues(issue_number, owner=owner, repo=repo_name)
            result["sub_issues"] = sub_issues
            result["sub_issues_count"] = len(sub_issues)

        return result

    # ========================================================================
    # Sub-Issue Operations (GitHub's native sub-issues feature)
    # ========================================================================

    def list_sub_issues(
        self,
        parent_issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List sub-issues of a parent issue.

        Args:
            parent_issue_number: Parent issue number
            owner: Repository owner
            repo: Repository name

        Returns:
            List of sub-issue summaries
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/issues/{parent_issue_number}/sub_issues",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return [
                {
                    "number": item["number"],
                    "id": item["id"],
                    "title": item["title"],
                    "state": item["state"],
                    "html_url": item["html_url"],
                }
                for item in data
            ]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No sub-issues or feature not enabled
                return []
            logger.error(f"Failed to list sub-issues: HTTP {e.response.status_code}")
            raise GithubException(e.response.status_code, e.response.json())
        except Exception as e:
            logger.error(f"Failed to list sub-issues: {e}")
            return []

    def add_sub_issue(
        self,
        parent_issue_number: int,
        child_issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an existing issue as a sub-issue to a parent.

        Args:
            parent_issue_number: Parent issue number
            child_issue_number: Child issue number to add as sub-issue
            owner: Repository owner
            repo: Repository name

        Returns:
            Result with parent and child info
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # First, get the child issue's internal ID (required by API)
        gh_repo = self._get_repo(owner, repo)
        child_issue = gh_repo.get_issue(child_issue_number)
        child_id = child_issue.id

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/issues/{parent_issue_number}/sub_issues",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={"sub_issue_id": child_id},
                    timeout=30.0,
                )
                response.raise_for_status()

            return {
                "success": True,
                "parent_issue": parent_issue_number,
                "child_issue": child_issue_number,
                "child_id": child_id,
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to add sub-issue: HTTP {e.response.status_code}")
            error_data = e.response.json() if e.response.content else {}
            raise GithubException(
                e.response.status_code,
                error_data,
                message=f"Failed to add #{child_issue_number} as sub-issue of #{parent_issue_number}",
            )

    def remove_sub_issue(
        self,
        parent_issue_number: int,
        child_issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove a sub-issue from a parent.

        Args:
            parent_issue_number: Parent issue number
            child_issue_number: Child issue number to remove
            owner: Repository owner
            repo: Repository name

        Returns:
            Result with parent and child info
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get the child issue's internal ID
        gh_repo = self._get_repo(owner, repo)
        child_issue = gh_repo.get_issue(child_issue_number)
        child_id = child_issue.id

        try:
            with httpx.Client() as client:
                response = client.delete(
                    f"https://api.github.com/repos/{owner}/{repo}/issues/{parent_issue_number}/sub_issues/{child_id}",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()

            return {
                "success": True,
                "parent_issue": parent_issue_number,
                "child_issue": child_issue_number,
                "removed": True,
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to remove sub-issue: HTTP {e.response.status_code}")
            error_data = e.response.json() if e.response.content else {}
            raise GithubException(
                e.response.status_code,
                error_data,
                message=f"Failed to remove #{child_issue_number} from #{parent_issue_number}",
            )

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

    # ========================================================================
    # Project Operations (GitHub Projects V2 via GraphQL)
    # ========================================================================

    def _graphql_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """
        Execute a GraphQL request against GitHub's API.

        Args:
            query: GraphQL query or mutation string
            variables: Optional variables for the query

        Returns:
            Response data dict

        Raises:
            GithubException: If the request fails
        """
        try:
            with httpx.Client() as client:
                response = client.post(
                    "https://api.github.com/graphql",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                    },
                    json={"query": query, "variables": variables or {}},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_messages = [e.get("message", str(e)) for e in data["errors"]]
                    raise GithubException(
                        400, {"message": "; ".join(error_messages)}, "GraphQL Error"
                    )

                return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"GraphQL request failed: HTTP {e.response.status_code}")
            raise GithubException(e.response.status_code, e.response.json())
        except GithubException:
            raise
        except Exception as e:
            logger.error(f"GraphQL request failed: {e}")
            raise GithubException(500, {"message": str(e)})

    def list_projects(
        self,
        owner: Optional[str] = None,
        is_org: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List GitHub Projects V2 for an organization or user.

        Args:
            owner: Organization or user name. Uses default_owner if not specified.
            is_org: If True, treat owner as organization. If False, treat as user.
            limit: Maximum projects to return (default: 20)

        Returns:
            List of project dicts with id, number, title, url, closed
        """
        owner = owner or self.default_owner
        if not owner:
            raise ValueError("Owner must be specified for listing projects")

        if is_org:
            query = """
            query($owner: String!, $limit: Int!) {
                organization(login: $owner) {
                    projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
                        nodes {
                            id
                            number
                            title
                            url
                            closed
                        }
                    }
                }
            }
            """
            data = self._graphql_request(query, {"owner": owner, "limit": limit})
            org = data.get("organization")
            if not org:
                # Try as user if org lookup fails
                return self.list_projects(owner=owner, is_org=False, limit=limit)
            nodes = org.get("projectsV2", {}).get("nodes", [])
        else:
            query = """
            query($owner: String!, $limit: Int!) {
                user(login: $owner) {
                    projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
                        nodes {
                            id
                            number
                            title
                            url
                            closed
                        }
                    }
                }
            }
            """
            data = self._graphql_request(query, {"owner": owner, "limit": limit})
            user = data.get("user")
            if not user:
                return []
            nodes = user.get("projectsV2", {}).get("nodes", [])

        return [
            {
                "id": node["id"],
                "number": node["number"],
                "title": node["title"],
                "url": node["url"],
                "closed": node["closed"],
            }
            for node in nodes
            if node  # Filter out None nodes
        ]

    def get_project_id(
        self,
        project: str,
        owner: Optional[str] = None,
        is_org: bool = True,
    ) -> Optional[str]:
        """
        Get the node ID of a project by number or title.

        Args:
            project: Project number (as string) or title
            owner: Organization or user name
            is_org: If True, treat owner as organization

        Returns:
            Project node ID or None if not found
        """
        owner = owner or self.default_owner
        if not owner:
            raise ValueError("Owner must be specified")

        # If project is a number, query directly
        if project.isdigit():
            project_number = int(project)
            if is_org:
                query = """
                query($owner: String!, $number: Int!) {
                    organization(login: $owner) {
                        projectV2(number: $number) {
                            id
                        }
                    }
                }
                """
                try:
                    data = self._graphql_request(
                        query, {"owner": owner, "number": project_number}
                    )
                except GithubException as e:
                    # Project not found - try as user or return None
                    if "Could not resolve" in str(e.data.get("message", "")):
                        return self.get_project_id(
                            project=project, owner=owner, is_org=False
                        )
                    raise
                org = data.get("organization")
                if not org:
                    # Try as user
                    return self.get_project_id(
                        project=project, owner=owner, is_org=False
                    )
                project_data = org.get("projectV2")
                return project_data["id"] if project_data else None
            else:
                query = """
                query($owner: String!, $number: Int!) {
                    user(login: $owner) {
                        projectV2(number: $number) {
                            id
                        }
                    }
                }
                """
                try:
                    data = self._graphql_request(
                        query, {"owner": owner, "number": project_number}
                    )
                except GithubException as e:
                    # Project not found
                    if "Could not resolve" in str(e.data.get("message", "")):
                        return None
                    raise
                user = data.get("user")
                if not user:
                    return None
                project_data = user.get("projectV2")
                return project_data["id"] if project_data else None

        # Project is a title - search through list
        projects = self.list_projects(owner=owner, is_org=is_org, limit=50)
        for p in projects:
            if p["title"].lower() == project.lower():
                return p["id"]

        return None

    def get_issue_node_id(
        self,
        issue_number: int,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> str:
        """
        Get the node ID of an issue (required for GraphQL mutations).

        Args:
            issue_number: Issue number
            owner: Repository owner
            repo: Repository name

        Returns:
            Issue node ID
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                issue(number: $number) {
                    id
                }
            }
        }
        """
        data = self._graphql_request(
            query, {"owner": owner, "repo": repo, "number": issue_number}
        )
        repository = data.get("repository")
        if not repository:
            raise GithubException(
                404, {"message": f"Repository {owner}/{repo} not found"}
            )
        issue = repository.get("issue")
        if not issue:
            raise GithubException(404, {"message": f"Issue #{issue_number} not found"})
        return issue["id"]

    def add_issue_to_project(
        self,
        issue_number: int,
        project: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        project_owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an issue to a GitHub Project V2.

        Args:
            issue_number: Issue number to add
            project: Project number (as string) or title
            owner: Repository owner (for the issue)
            repo: Repository name
            project_owner: Owner of the project (org or user). Defaults to repo owner.

        Returns:
            Dict with project_item_id and success status
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        project_owner = project_owner or owner

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get issue node ID
        issue_node_id = self.get_issue_node_id(issue_number, owner=owner, repo=repo)

        # Get project node ID
        project_id = self.get_project_id(project, owner=project_owner, is_org=True)
        if not project_id:
            raise GithubException(
                404, {"message": f"Project '{project}' not found for {project_owner}"}
            )

        # Add to project using mutation
        mutation = """
        mutation($projectId: ID!, $contentId: ID!) {
            addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                item {
                    id
                }
            }
        }
        """
        data = self._graphql_request(
            mutation, {"projectId": project_id, "contentId": issue_node_id}
        )

        item = data.get("addProjectV2ItemById", {}).get("item")
        return {
            "success": True,
            "issue_number": issue_number,
            "project": project,
            "project_item_id": item["id"] if item else None,
        }

    def remove_issue_from_project(
        self,
        issue_number: int,
        project: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        project_owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Remove an issue from a GitHub Project V2.

        Args:
            issue_number: Issue number to remove
            project: Project number (as string) or title
            owner: Repository owner (for the issue)
            repo: Repository name
            project_owner: Owner of the project (org or user). Defaults to repo owner.

        Returns:
            Dict with success status
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        project_owner = project_owner or owner

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get project node ID
        project_id = self.get_project_id(project, owner=project_owner, is_org=True)
        if not project_id:
            raise GithubException(
                404, {"message": f"Project '{project}' not found for {project_owner}"}
            )

        # Get issue node ID
        issue_node_id = self.get_issue_node_id(issue_number, owner=owner, repo=repo)

        # First, find the project item ID for this issue
        query = """
        query($projectId: ID!, $cursor: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: 100, after: $cursor) {
                        nodes {
                            id
                            content {
                                ... on Issue {
                                    id
                                    number
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        # Paginate to find the item
        cursor = None
        item_id = None
        while True:
            data = self._graphql_request(
                query, {"projectId": project_id, "cursor": cursor}
            )
            node = data.get("node", {})
            items = node.get("items", {})

            for item in items.get("nodes", []):
                content = item.get("content")
                if content and content.get("id") == issue_node_id:
                    item_id = item["id"]
                    break

            if item_id:
                break

            page_info = items.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        if not item_id:
            raise GithubException(
                404,
                {"message": f"Issue #{issue_number} not found in project '{project}'"},
            )

        # Delete the item from project
        mutation = """
        mutation($projectId: ID!, $itemId: ID!) {
            deleteProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
                deletedItemId
            }
        }
        """
        data = self._graphql_request(
            mutation, {"projectId": project_id, "itemId": item_id}
        )

        deleted_id = data.get("deleteProjectV2Item", {}).get("deletedItemId")
        return {
            "success": True,
            "issue_number": issue_number,
            "project": project,
            "deleted_item_id": deleted_id,
        }

    def get_project_fields(
        self,
        project: str,
        owner: Optional[str] = None,
        is_org: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get fields for a GitHub Project V2 with options for SingleSelect fields.

        Args:
            project: Project number (as string) or title
            owner: Organization or user name
            is_org: If True, treat owner as organization

        Returns:
            List of field dicts with id, name, data_type, and options for SingleSelect
        """
        owner = owner or self.default_owner
        if not owner:
            raise ValueError("Owner must be specified")

        # Get project ID first
        project_id = self.get_project_id(project, owner=owner, is_org=is_org)
        if not project_id:
            raise GithubException(
                404, {"message": f"Project '{project}' not found for {owner}"}
            )

        # Query fields with options
        query = """
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    fields(first: 100) {
                        nodes {
                            ... on ProjectV2FieldCommon {
                                id
                                name
                                dataType
                            }
                            ... on ProjectV2SingleSelectField {
                                options {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        data = self._graphql_request(query, {"projectId": project_id})

        node = data.get("node")
        if not node:
            return []

        fields = []
        for field in node.get("fields", {}).get("nodes", []):
            if not field:
                continue

            field_data = {
                "id": field.get("id"),
                "name": field.get("name"),
                "data_type": field.get("dataType"),
            }

            # Add options for SingleSelect fields
            if "options" in field:
                field_data["options"] = [
                    {"id": opt["id"], "name": opt["name"]}
                    for opt in field.get("options", [])
                ]

            fields.append(field_data)

        return fields

    def list_projects_with_fields(
        self,
        owner: Optional[str] = None,
        is_org: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List GitHub Projects V2 with their fields in one GraphQL call.

        More efficient than calling list_projects + get_project_fields separately.

        Args:
            owner: Organization or user name. Uses default_owner if not specified.
            is_org: If True, treat owner as organization. If False, treat as user.
            limit: Maximum projects to return (default: 20)

        Returns:
            List of project dicts with id, number, title, url, closed, owner, fields
        """
        owner = owner or self.default_owner
        if not owner:
            raise ValueError("Owner must be specified for listing projects")

        if is_org:
            query = """
            query($owner: String!, $limit: Int!) {
                organization(login: $owner) {
                    projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
                        nodes {
                            id
                            number
                            title
                            url
                            closed
                            fields(first: 50) {
                                nodes {
                                    ... on ProjectV2FieldCommon {
                                        id
                                        name
                                        dataType
                                    }
                                    ... on ProjectV2SingleSelectField {
                                        options {
                                            id
                                            name
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            data = self._graphql_request(query, {"owner": owner, "limit": limit})
            org = data.get("organization")
            if not org:
                # Try as user if org lookup fails
                return self.list_projects_with_fields(
                    owner=owner, is_org=False, limit=limit
                )
            nodes = org.get("projectsV2", {}).get("nodes", [])
        else:
            query = """
            query($owner: String!, $limit: Int!) {
                user(login: $owner) {
                    projectsV2(first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
                        nodes {
                            id
                            number
                            title
                            url
                            closed
                            fields(first: 50) {
                                nodes {
                                    ... on ProjectV2FieldCommon {
                                        id
                                        name
                                        dataType
                                    }
                                    ... on ProjectV2SingleSelectField {
                                        options {
                                            id
                                            name
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            data = self._graphql_request(query, {"owner": owner, "limit": limit})
            user = data.get("user")
            if not user:
                return []
            nodes = user.get("projectsV2", {}).get("nodes", [])

        projects = []
        for node in nodes:
            if not node:
                continue

            # Parse fields
            fields = []
            for field in node.get("fields", {}).get("nodes", []):
                if not field:
                    continue

                field_data = {
                    "id": field.get("id"),
                    "name": field.get("name"),
                    "data_type": field.get("dataType"),
                }

                # Add options for SingleSelect fields
                if "options" in field:
                    field_data["options"] = [
                        {"id": opt["id"], "name": opt["name"]}
                        for opt in field.get("options", [])
                    ]

                fields.append(field_data)

            projects.append(
                {
                    "id": node["id"],
                    "number": node["number"],
                    "title": node["title"],
                    "url": node["url"],
                    "closed": node["closed"],
                    "owner": owner,
                    "fields": fields,
                }
            )

        return projects

    def get_project_item_id(
        self,
        issue_number: int,
        project: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        project_owner: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the project item ID for an issue in a project.

        The project item ID is required for updating field values.

        Args:
            issue_number: Issue number
            project: Project number (as string) or title
            owner: Repository owner (for the issue)
            repo: Repository name
            project_owner: Owner of the project (org or user). Defaults to repo owner.

        Returns:
            Project item ID or None if issue not in project
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        project_owner = project_owner or owner

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get project ID
        project_id = self.get_project_id(project, owner=project_owner, is_org=True)
        if not project_id:
            raise GithubException(
                404, {"message": f"Project '{project}' not found for {project_owner}"}
            )

        # Get issue node ID
        issue_node_id = self.get_issue_node_id(issue_number, owner=owner, repo=repo)

        # Search for the item in the project
        query = """
        query($projectId: ID!, $cursor: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: 100, after: $cursor) {
                        nodes {
                            id
                            content {
                                ... on Issue {
                                    id
                                    number
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        cursor = None
        while True:
            data = self._graphql_request(
                query, {"projectId": project_id, "cursor": cursor}
            )
            node = data.get("node", {})
            items = node.get("items", {})

            for item in items.get("nodes", []):
                content = item.get("content")
                if content and content.get("id") == issue_node_id:
                    return item["id"]

            page_info = items.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        return None

    def update_project_item_field(
        self,
        issue_number: int,
        project: str,
        field_name: str,
        value: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        project_owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a field value for an issue in a GitHub Project V2.

        Supports different field types:
        - SINGLE_SELECT: value is the option name (e.g., "In Progress")
        - TEXT: value is the text content
        - NUMBER: value is the number as string
        - DATE: value is ISO date format (YYYY-MM-DD)

        Args:
            issue_number: Issue number
            project: Project number (as string) or title
            field_name: Field name (e.g., "Status", "Priority")
            value: Field value (option name for SingleSelect, text for others)
            owner: Repository owner (for the issue)
            repo: Repository name
            project_owner: Owner of the project (org or user). Defaults to repo owner.

        Returns:
            Dict with success status and updated info

        Raises:
            GithubException: If project, field, or option not found
        """
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        project_owner = project_owner or owner

        if not owner or not repo:
            raise ValueError("Repository owner and name must be specified")

        # Get project ID
        project_id = self.get_project_id(project, owner=project_owner, is_org=True)
        if not project_id:
            raise GithubException(
                404, {"message": f"Project '{project}' not found for {project_owner}"}
            )

        # Get project item ID (issue must be in project)
        item_id = self.get_project_item_id(
            issue_number=issue_number,
            project=project,
            owner=owner,
            repo=repo,
            project_owner=project_owner,
        )
        if not item_id:
            raise GithubException(
                404,
                {
                    "message": f"Issue #{issue_number} not found in project '{project}'. Add it first with add_to_project."
                },
            )

        # Get fields to find the field ID and type
        fields = self.get_project_fields(project, owner=project_owner, is_org=True)

        # Find the field by name (case-insensitive)
        field = None
        for f in fields:
            if f["name"].lower() == field_name.lower():
                field = f
                break

        if not field:
            available_fields = [f["name"] for f in fields]
            raise GithubException(
                404,
                {
                    "message": f"Field '{field_name}' not found in project. Available fields: {available_fields}"
                },
            )

        field_id = field["id"]
        data_type = field.get("data_type")

        # Build the value based on field type
        if data_type == "SINGLE_SELECT":
            # Find the option ID by name
            options = field.get("options", [])
            option_id = None
            for opt in options:
                if opt["name"].lower() == value.lower():
                    option_id = opt["id"]
                    break

            if not option_id:
                available_options = [opt["name"] for opt in options]
                raise GithubException(
                    400,
                    {
                        "message": f"Option '{value}' not found for field '{field_name}'. Available options: {available_options}"
                    },
                )

            field_value = {"singleSelectOptionId": option_id}

        elif data_type == "TEXT":
            field_value = {"text": value}

        elif data_type == "NUMBER":
            try:
                field_value = {"number": float(value)}
            except ValueError:
                raise GithubException(
                    400,
                    {
                        "message": f"Invalid number value '{value}' for field '{field_name}'"
                    },
                )

        elif data_type == "DATE":
            field_value = {"date": value}

        else:
            raise GithubException(
                400,
                {
                    "message": f"Field type '{data_type}' not supported for updates. Supported: SINGLE_SELECT, TEXT, NUMBER, DATE"
                },
            )

        # Execute the mutation
        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId,
                itemId: $itemId,
                fieldId: $fieldId,
                value: $value
            }) {
                projectV2Item {
                    id
                }
            }
        }
        """

        data = self._graphql_request(
            mutation,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "value": field_value,
            },
        )

        updated_item = data.get("updateProjectV2ItemFieldValue", {}).get(
            "projectV2Item"
        )

        return {
            "success": True,
            "issue_number": issue_number,
            "project": project,
            "field": field_name,
            "value": value,
            "item_id": updated_item["id"] if updated_item else item_id,
        }
