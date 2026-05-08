"""Executable EDIM model runtime package.

This package is intentionally callable as a process boundary. Backend code should
launch it through a runtime adapter rather than importing model internals.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
