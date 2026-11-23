class DraftVersionConflict(RuntimeError):
    """Raised when a draft update uses a stale version."""
