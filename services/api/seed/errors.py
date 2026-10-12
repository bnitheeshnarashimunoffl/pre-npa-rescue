class SeedError(RuntimeError):
    """Seeding cannot proceed (missing files, wrong columns, non-empty database)."""
