import os
from services import SummarizerFactory

def categorize_and_summarize(text: str, url: str) -> dict:
    """
    Facade function maintaining backward compatibility while 
    delegating work to the underlying OOP SummarizerFactory.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    summarizer = SummarizerFactory.get_summarizer(url=url, raw_text=text)
    return summarizer.process_and_summarize(api_key=api_key)

if __name__ == "__main__":
    res = categorize_and_summarize("Test content", "https://youtube.com/watch?v=123")
    print("FACADE TEST RESULT:", res)