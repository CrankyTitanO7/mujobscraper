"""Source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import JobPosting
from ..utils.http import HttpClient


class JobSource(ABC):
    """A provider of normalized job postings."""

    name: str

    @abstractmethod
    def fetch(self, client: HttpClient) -> list[JobPosting]:
        """Fetch postings. Adapters may make several HTTP requests."""
