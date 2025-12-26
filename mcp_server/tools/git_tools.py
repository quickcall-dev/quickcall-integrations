"""
Git Tools - Simple tools for viewing repository changes.
"""

from typing import Optional, List
import subprocess

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
            repo_name = f"{repo_info['owner']}/{repo_info['repo']}" if repo_info['owner'] else repo_info['root']

            result = {
                "repository": repo_name,
                "branch": repo_info['branch'],
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
                    commits.append({
                        "sha": parts[0][:7],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    })

            result["commits"] = commits
            result["commit_count"] = len(commits)

            if not commits:
                result["diff"] = {"files_changed": 0, "additions": 0, "deletions": 0, "patch": ""}
                return result

            # Get total diff between oldest and newest commit
            oldest_sha = commits[-1]["sha"]
            newest_sha = commits[0]["sha"]

            try:
                # Get stats
                numstat = _run_git(["diff", "--numstat", f"{oldest_sha}^", newest_sha], path)

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
                        files.append({
                            "file": parts[2],
                            "additions": adds,
                            "deletions": dels,
                        })
                        total_add += adds
                        total_del += dels

                # Get actual diff patch
                diff_patch = _run_git(["diff", f"{oldest_sha}^", newest_sha], path)

                # Truncate if too large
                if len(diff_patch) > 50000:
                    diff_patch = diff_patch[:50000] + "\n\n... (truncated, diff too large)"

                result["diff"] = {
                    "files_changed": len(files),
                    "additions": total_add,
                    "deletions": total_del,
                    "files": files[:30],
                    "patch": diff_patch,
                }
            except ToolError:
                result["diff"] = {"files_changed": 0, "additions": 0, "deletions": 0, "patch": ""}

            # Uncommitted changes
            staged = _run_git(["diff", "--cached", "--name-only"], path)
            unstaged = _run_git(["diff", "--name-only"], path)

            staged_list = [f for f in staged.split("\n") if f]
            unstaged_list = [f for f in unstaged.split("\n") if f]

            if staged_list or unstaged_list:
                # Get uncommitted diff patch too
                uncommitted_patch = _run_git(["diff", "HEAD"], path)
                if len(uncommitted_patch) > 20000:
                    uncommitted_patch = uncommitted_patch[:20000] + "\n\n... (truncated)"

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
