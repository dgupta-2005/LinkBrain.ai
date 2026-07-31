from urllib.parse import urlparse
from .base_summarizer import BaseSummarizer
from .summarizers import YouTubeSummarizer, InstagramSummarizer, GenericWebSummarizer

class SummarizerFactory:
    """Factory class responsible for instantiating concrete summarizers based on URL domain."""

    @staticmethod
    def get_summarizer(url: str, raw_text: str = "") -> BaseSummarizer:
        url_lower = url.lower()
        
        if any(domain in url_lower for domain in ["youtube.com", "youtu.be"]):
            return YouTubeSummarizer(url, raw_text)
        elif "instagram.com" in url_lower:
            return InstagramSummarizer(url, raw_text)
        else:
            return GenericWebSummarizer(url, raw_text)

    @staticmethod
    def detect_platform_name(url: str) -> str:
        """Extracts normalized platform category names."""
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        if "instagram.com" in domain:
            return "Instagram"
        elif "twitter.com" in domain or "x.com" in domain:
            return "Twitter"
        elif "youtube.com" in domain or "youtu.be" in domain:
            return "YouTube"
        elif "linkedin.com" in domain:
            return "LinkedIn"
        else:
            try:
                parts = domain.split('.')
                main_word = parts[1] if parts[0] in ['www', 'm', 'en', 'mobile'] and len(parts) > 1 else parts[0]
                return main_word.title()
            except Exception:
                return "Web"