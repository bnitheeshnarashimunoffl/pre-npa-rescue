"""Synthetic data generator, feature pipeline and experiment simulator (WS1).

Public API: :class:`DatagenConfig`. Run the pipeline with ``uv run datagen --help``.
"""

from datagen.config import DatagenConfig

__all__ = ["DatagenConfig", "__version__"]

__version__ = "0.1.0"
