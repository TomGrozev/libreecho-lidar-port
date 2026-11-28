"""Error types for the Lidar boot-chain restore tool.

Every failure the tool raises on purpose derives from RestoreError so the CLI
can report it without a traceback. Anything else is a bug.
"""


class RestoreError(Exception):
    """Base class for validation, guard, backend, and apply failures."""


class ManifestError(RestoreError):
    """The manifest or plan does not match its schema."""


class GuardError(RestoreError):
    """A safety guard refused the request before any write happened."""


class BackendError(RestoreError):
    """The device backend failed, returned short data, or is unavailable."""


class BackendWriteRefused(BackendError):
    """The backend is read-only in this phase and will not write."""


class JournalError(RestoreError):
    """The resume journal is corrupt or belongs to another plan."""


class ReadbackError(RestoreError):
    """Readback after a write did not match the bytes that were written."""
