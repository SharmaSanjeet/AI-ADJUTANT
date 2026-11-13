class NotFoundError(Exception):
    """Requested domain object does not exist."""


class ConflictError(Exception):
    """State transition is not allowed from the current state."""


class PolicyViolation(Exception):
    """A human-only or policy-gated action was attempted improperly."""
