"""Project-wide exception types.

All expected failures inherit from :class:`JobscraperError` so the CLI can turn
them into a single readable error message instead of a traceback.
"""


class JobscraperError(Exception):
    """Base class for expected jobscraper failures."""


class ConfigError(JobscraperError):
    """Configuration is missing, malformed, or internally inconsistent."""


class DataError(JobscraperError):
    """A data table contains a value that cannot be interpreted."""


class SourceError(JobscraperError):
    """A job source could not be fetched or parsed."""


class FetchError(JobscraperError):
    """An HTTP request failed after retries."""


class LLMError(JobscraperError):
    """An LLM request failed."""


class LLMUnavailableError(LLMError):
    """No usable LLM provider is configured."""


class BrowserError(JobscraperError):
    """Browser automation could not start or complete."""
