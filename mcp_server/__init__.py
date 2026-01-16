"""
MCP Server for QuickCall
GitHub integration tools for AI assistant
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("quickcall-integrations")
except PackageNotFoundError:
    # Package not installed (development mode)
    __version__ = "0.0.0-dev"
