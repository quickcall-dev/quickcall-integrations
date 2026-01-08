"""
Git Tools - Simple tools for viewing repository changes.
"""

from typing import Optional, List
import subprocess
import re

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field


def _run_git(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ToolError(f"Git error: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise ToolError("Git command timed out")
    except FileNotFoundError:
        raise ToolError("Git not found")


def _get_repo_info(cwd: Optional[str] = None) -> dict:
    """Get repository info."""
    try:
        _run_git(["rev-parse", "--git-dir"], cwd)
    except ToolError:
        raise ToolError(f"Not a git repository: {cwd or 'current directory'}")

    repo_root = _run_git(["rev-parse", "--show-toplevel"], cwd)

    try:
        remote_url = _run_git(["remote", "get-url", "origin"], cwd)
        if "github.com" in remote_url:
            if remote_url.startswith("git@"):
                path = remote_url.split(":")[-1]
            else:
                path = remote_url.split("github.com/")[-1]
            path = path.rstrip(".git")
            parts = path.split("/")
            owner, repo = (parts[0], parts[1]) if len(parts) >= 2 else (None, None)
        else:
            owner, repo = None, None
    except ToolError:
        owner, repo = None, None

    try:
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    except ToolError:
        branch = "unknown"

    return {"root": repo_root, "owner": owner, "repo": repo, "branch": branch}


def create_git_tools(mcp: FastMCP) -> None:
    """Add git tools to the MCP server."""

    @mcp.tool(tags={"git", "updates"})
    def get_updates(
        path: str = Field(
            ...,
            description="Path to git repository. Use the user's current working directory.",
        ),
        days: int = Field(
            default=7,
            description="Number of days to look back (default: 7)",
        ),
        author: Optional[str] = Field(
            default=None,
            description="Filter by author name/email",
        ),
    ) -> dict:
        """
        Get updates from a git repository. Returns commits, diff stats, and uncommitted changes.

        FORMAT OUTPUT AS A STANDUP SUMMARY:

        **Summary:** One sentence of what was accomplished.

        **What I worked on:**
        - Bullet points of key changes (group related commits)
        - Focus on features/fixes, not individual commits
        - Use past tense action verbs

        **In Progress:**
        - Any uncommitted changes (what's being worked on now)

        **Blockers:** Only mention if there are merge conflicts or issues visible.

        Never display raw JSON to the user.
        """
        try:
            repo_info = _get_repo_info(path)
            repo_name = (
                f"{repo_info['owner']}/{repo_info['repo']}"
                if repo_info["owner"]
                else repo_info["root"]
            )

            result = {
                "repository": repo_name,
                "branch": repo_info["branch"],
                "period": f"Last {days} days",
            }

            # Get commits
            since_date = f"{days} days ago"
            log_format = "--pretty=format:%H|%an|%ad|%s"
            log_args = ["log", log_format, "--date=short", f"--since={since_date}"]
            if author:
                log_args.extend(["--author", author])

            log_output = _run_git(log_args, path)

            commits = []
            for line in log_output.split("\n"):
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    commits.append(
                        {
                            "sha": parts[0][:7],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3],
                        }
                    )

            result["commits"] = commits
            result["commit_count"] = len(commits)

            if not commits:
                result["diff"] = {
                    "files_changed": 0,
                    "additions": 0,
                    "deletions": 0,
                    "patch": "",
                }
                return result

            # Get total diff between oldest and newest commit
            oldest_sha = commits[-1]["sha"]
            newest_sha = commits[0]["sha"]

            try:
                # Get stats
                numstat = _run_git(
                    ["diff", "--numstat", f"{oldest_sha}^", newest_sha], path
                )

                files = []
                total_add = 0
                total_del = 0

                for line in numstat.split("\n"):
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        adds = int(parts[0]) if parts[0] != "-" else 0
                        dels = int(parts[1]) if parts[1] != "-" else 0
                        files.append(
                            {
                                "file": parts[2],
                                "additions": adds,
                                "deletions": dels,
                            }
                        )
                        total_add += adds
                        total_del += dels

                # Get actual diff patch
                diff_patch = _run_git(["diff", f"{oldest_sha}^", newest_sha], path)

                # Truncate if too large
                if len(diff_patch) > 50000:
                    diff_patch = (
                        diff_patch[:50000] + "\n\n... (truncated, diff too large)"
                    )

                result["diff"] = {
                    "files_changed": len(files),
                    "additions": total_add,
                    "deletions": total_del,
                    "files": files[:30],
                    "patch": diff_patch,
                }
            except ToolError:
                result["diff"] = {
                    "files_changed": 0,
                    "additions": 0,
                    "deletions": 0,
                    "patch": "",
                }

            # Uncommitted changes
            staged = _run_git(["diff", "--cached", "--name-only"], path)
            unstaged = _run_git(["diff", "--name-only"], path)

            staged_list = [f for f in staged.split("\n") if f]
            unstaged_list = [f for f in unstaged.split("\n") if f]

            if staged_list or unstaged_list:
                # Get uncommitted diff patch too
                uncommitted_patch = _run_git(["diff", "HEAD"], path)
                if len(uncommitted_patch) > 20000:
                    uncommitted_patch = (
                        uncommitted_patch[:20000] + "\n\n... (truncated)"
                    )

                result["uncommitted"] = {
                    "staged": staged_list,
                    "unstaged": unstaged_list,
                    "patch": uncommitted_patch,
                }

            return result

        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to get updates: {str(e)}")

    @mcp.tool(tags={"git", "appraisal"})
    def get_local_contributions(
        path: str = Field(
            ...,
            description="Path to git repository.",
        ),
        days: int = Field(
            default=180,
            description="Number of days to look back (default: 180 for 6 months)",
        ),
        author: Optional[str] = Field(
            default=None,
            description="Filter by author name/email. If not specified, uses git config user.email",
        ),
    ) -> dict:
        """
        Get contributions from local git history for appraisals.

        Returns commits with:
        - commit message (for Claude to categorize: feat, fix, chore, etc.)
        - PR number (extracted from merge commits if available)
        - stats (additions, deletions)
        - date range

        Claude should analyze commit messages to categorize contributions.
        This tool does NOT do any categorization - it returns raw data.

        Use this for appraisals when:
        - GitHub App is not connected
        - You want local repo contributions only
        - Testing appraisal features on cloned repos
        """
        try:
            repo_info = _get_repo_info(path)
            repo_name = (
                f"{repo_info['owner']}/{repo_info['repo']}"
                if repo_info["owner"]
                else repo_info["root"]
            )

            # Get author from git config if not specified
            if not author:
                try:
                    author = _run_git(["config", "user.email"], path)
                except ToolError:
                    pass

            since_date = f"{days} days ago"

            # Get all commits by author
            log_format = "--pretty=format:%H|%an|%ae|%ad|%s|%b---COMMIT_END---"
            log_args = [
                "log",
                log_format,
                "--date=iso",
                f"--since={since_date}",
            ]
            if author:
                log_args.extend(["--author", author])

            log_output = _run_git(log_args, path)

            commits = []
            merge_commits = []

            # Parse commits
            for commit_block in log_output.split("---COMMIT_END---"):
                if not commit_block.strip():
                    continue

                lines = commit_block.strip().split("|", 5)
                if len(lines) < 5:
                    continue

                sha = lines[0]
                author_name = lines[1]
                author_email = lines[2]
                date = lines[3]
                subject = lines[4]
                body = lines[5] if len(lines) > 5 else ""

                # Extract PR number from merge commit message
                pr_number = None
                merge_match = re.search(r"Merge pull request #(\d+)", subject)
                if merge_match:
                    pr_number = int(merge_match.group(1))
                else:
                    # Also check for GitHub's squash merge format
                    squash_match = re.search(r"\(#(\d+)\)$", subject)
                    if squash_match:
                        pr_number = int(squash_match.group(1))

                commit_data = {
                    "sha": sha[:7],
                    "full_sha": sha,
                    "author": author_name,
                    "email": author_email,
                    "date": date,
                    "message": subject,
                    "body": body.strip()[:500] if body else "",
                    "pr_number": pr_number,
                }

                commits.append(commit_data)

                if pr_number:
                    merge_commits.append(commit_data)

            # Get stats for commits if we have any
            stats = {"total_additions": 0, "total_deletions": 0, "files_changed": set()}

            if commits:
                # Get numstat for all commits by this author
                numstat_args = [
                    "log",
                    "--numstat",
                    "--pretty=format:",
                    f"--since={since_date}",
                ]
                if author:
                    numstat_args.extend(["--author", author])

                try:
                    numstat_output = _run_git(numstat_args, path)
                    for line in numstat_output.split("\n"):
                        if not line.strip():
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            adds = int(parts[0]) if parts[0] != "-" else 0
                            dels = int(parts[1]) if parts[1] != "-" else 0
                            stats["total_additions"] += adds
                            stats["total_deletions"] += dels
                            stats["files_changed"].add(parts[2])
                except ToolError:
                    pass

            # Calculate date range
            if commits:
                dates = [c["date"] for c in commits]
                earliest = min(dates)
                latest = max(dates)
            else:
                earliest = latest = None

            return {
                "repository": repo_name,
                "branch": repo_info["branch"],
                "author": author,
                "period_days": days,
                "date_range": {
                    "earliest": earliest,
                    "latest": latest,
                },
                "summary": {
                    "total_commits": len(commits),
                    "merge_commits": len(merge_commits),
                    "unique_prs": len(
                        set(c["pr_number"] for c in merge_commits if c["pr_number"])
                    ),
                    "total_additions": stats["total_additions"],
                    "total_deletions": stats["total_deletions"],
                    "files_touched": len(stats["files_changed"]),
                },
                "commits": commits,
                "pr_commits": merge_commits,
            }

        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to get contributions: {str(e)}")
