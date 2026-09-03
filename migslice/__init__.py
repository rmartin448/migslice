"""migslice: pull a single migration's SQL out of a concatenated stream."""

from .parser import extract, iter_migrations, list_ids

__version__ = "0.1.0"
__all__ = ["extract", "iter_migrations", "list_ids", "__version__"]
