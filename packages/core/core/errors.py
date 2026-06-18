class StoryWeaverError(Exception):
    """Base class for all domain errors."""


class AccessDeniedError(StoryWeaverError):
    """Raised when a user attempts to access a resource they do not own."""


class ProviderUnavailableError(StoryWeaverError):
    """Raised when an external AI or storage provider cannot be reached."""


class EntityNotFoundError(StoryWeaverError):
    """Raised when a requested entity does not exist in the database."""


class CampaignJoinError(StoryWeaverError):
    """Raised when a campaign join attempt fails (e.g., invalid join code)."""


class ValidationError(StoryWeaverError):
    """Raised when entity data fails domain validation rules."""