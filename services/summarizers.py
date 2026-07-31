import os
import json
import requests
from typing import Dict, Any
from .base_summarizer import BaseSummarizer

class YouTubeSummarizer(BaseSummarizer):
    """Specialized engine for YouTube video links using YouTube oEmbed API."""

    def extract_metadata(self) -> None:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={self._url}&format=json"
            res = requests.get(oembed_url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                self._title = data.get('title', '')
                self._description = f"Video by {data.get('author_name', 'YouTube Creator')}"
        except Exception as e:
            print(f"[YouTubeSummarizer] Metadata extraction failed: {e}")

    def process_and_summarize(self, api_key: str) -> Dict[str, Any]:
        self.extract_metadata()
        combined_text = f"{self._raw_text}\n\n[Extracted YouTube Metadata]\nTitle: {self._title}\nDescription: {self._description}"
        return _execute_gemini_query(self._url, combined_text, api_key)


class InstagramSummarizer(BaseSummarizer):
    """Specialized engine for Instagram posts and reels."""

    def extract_metadata(self) -> None:
        try:
            res = requests.get(f"https://api.microlink.io?url={self._url}", timeout=5)
            if res.status_code == 200:
                data = res.json().get('data', {})
                title = data.get('title', '')
                if title.lower() not in ["instagram", "login • instagram"]:
                    self._title = title
                    self._description = data.get('description', '')
        except Exception as e:
            print(f"[InstagramSummarizer] Metadata extraction failed: {e}")

    def process_and_summarize(self, api_key: str) -> Dict[str, Any]:
        self.extract_metadata()
        
        # Hard-stop safeguard if content is completely inaccessible
        if not self._title:
            return {
                "summary": "Failed to generate & extract info, please edit manually (by edit button card)",
                "category": "Others"
            }
            
        combined_text = f"{self._raw_text}\n\n[Extracted Instagram Data]\nTitle: {self._title}\nDescription: {self._description}"
        return _execute_gemini_query(self._url, combined_text, api_key)


class GenericWebSummarizer(BaseSummarizer):
    """Fallback engine for general internet articles, blogs, and documentation."""

    def extract_metadata(self) -> None:
        try:
            res = requests.get(f"https://api.microlink.io?url={self._url}", timeout=5)
            if res.status_code == 200:
                data = res.json().get('data', {})
                self._title = data.get('title', '')
                self._description = data.get('description', '')
        except Exception as e:
            print(f"[GenericWebSummarizer] Metadata extraction failed: {e}")

    def process_and_summarize(self, api_key: str) -> Dict[str, Any]:
        self.extract_metadata()
        combined_text = f"{self._raw_text}\n\n[Extracted Web Data]\nTitle: {self._title}\nDescription: {self._description}"
        return _execute_gemini_query(self._url, combined_text, api_key)


def _execute_gemini_query(url: str, text: str, api_key: str) -> Dict[str, Any]:
    """Internal helper encapsulating direct REST calls to Gemini models."""
    if not api_key:
        return {"summary": "Gemini API Key missing.", "category": "Uncategorized"}

    prompt = f'''
    You are an expert Content Classifier and AI assistant for a "Social Saver" application. 
    Analyze the following content or URL:
    INPUT DATA:
    URL: {url}
    Content Snippet: {text}

    INSTRUCTIONS:
    1. ANALYZE: Review the URL structure and keywords.
    2. SUMMARIZE: Create a 1-sentence summary (max 15 words) focusing on the "Action" or "Main Value".
    3. CATEGORIZE: Select the SINGLE most accurate category from industry tags:
       [Coding, AI, Machine Learning, Fitness, Math, Food, Travel, Design, Finance, Career, Courses, Productivity, Fashion, Humor, Business, Entertainment, Sports, Health, Education, Technology, Science, News, Politics, World, Others].

    OUTPUT FORMAT: Return ONLY a JSON object: {{"summary": "...", "category": "..."}}
    '''

    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-pro", "gemini-flash-latest"]
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
        ]
    }

    for model in models:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                text_resp = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                start, end = text_resp.find('{'), text_resp.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(text_resp[start:end+1])
        except Exception:
            continue

    return {"summary": "Failed to generate & extract info, please edit manually (by edit button card)", "category": "Others"}