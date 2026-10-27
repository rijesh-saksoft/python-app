"""What "ready" means for this service.

Add a check here for each thing the service needs (database, model provider, ...).
Each check returns a short problem text, or nothing when all is well.
"""


def check_dependencies() -> list[str]:
    """Return a list of problems. An empty list means ready.

    TODO(trainee, day 7 and 11): add a database check here, for example open a connection
    with a short timeout and run `SELECT 1`. Always use a timeout (PY-12).
    """
    return []
