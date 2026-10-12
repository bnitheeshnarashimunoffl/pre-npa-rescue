"""Shared contracts for Pre-NPA Rescue (owned by WS5).

Change process: see ``contracts/README.md`` (A10.2). Never rename or remove a field
without a contract-change issue and a CHANGELOG entry.
"""

from typing import Final

CONTRACT_VERSION: Final = "0.1.1"
__version__: Final = CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION", "__version__"]
