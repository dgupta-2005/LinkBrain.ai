from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseSummarizer(ABC):
    """
    Abstract Base Class defining the contract for all platform summarizers.
    Exposes a unified interface while hiding complex scraping and parsing details.
    """

    def __init__(self, url: str, raw_text: str = ""):
        self._url = url
        self._raw_text = raw_text
        self._title = ""
        self._description = ""

    @property
    def url(self) -> str:
        return self._url

    @property
    def raw_text(self) -> str:
        return self._raw_text

    @abstractmethod
    def extract_metadata(self) -> None:
        """Fetch platform-specific metadata (e.g. oEmbed, Microlink, or Scrapers)."""
        pass

    @abstractmethod
    def process_and_summarize(self, api_key: str) -> Dict[str, Any]:
        """Execute Gemini AI classification and return structured results."""
        pass