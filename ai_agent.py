import os
import json
import requests
from dotenv import load_dotenv
load_dotenv()
def categorize_and_summarize(text: str, url: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"summary": "Gemini API Key missing.", "category": "Uncategorized"}
        
    # Safe Mode: Identified for social links
    is_social = any(domain in url.lower() for domain in ["instagram.com", "reels", "youtube.com", "youtu.be"])
    is_youtube = any(domain in url.lower() for domain in ["youtube.com", "youtu.be"])
    
    try:
        res = requests.get(f"https://api.microlink.io?url={url}", timeout=5)
        if res.status_code == 200:
            microlink_data = res.json().get('data', {})
            title = microlink_data.get('title', '')
            desc = microlink_data.get('description', '')
            
            # STAGE 1: Check for explicit "Generic/Blocked" pages
            generic_titles = ["instagram", "login • instagram", "youtube", "login - youtube"]
            if is_social and title.lower() in generic_titles:
                title = "" # Force fallback for generic junk

        # STAGE 2: YouTube-Specific Scraper (Prioritize this over Microlink)
        if is_youtube:
            oembed_res = requests.get(f"https://www.youtube.com/oembed?url={url}&format=json", timeout=5)
            if oembed_res.status_code == 200:
                oembed_data = oembed_res.json()
                # Overwrite anything Microlink said with the real YouTube Data
                title = oembed_data.get('title', '')
                desc = f"Video by {oembed_data.get('author_name', 'YouTube Creator')}"
            else:
                print(f"YouTube oEmbed failed with status: {oembed_res.status_code}")

        if title or desc:
            text = f"{text}\n\n[Extracted Web Data]\nTitle: {title}\nDescription: {desc}"
            
    except Exception as e:
        print(f"Metadata extraction failed: {e}")

    # STAGE 3: If it's a social link and we STILL have absolutely ZERO info, skip AI
    # This is a hard-stop to prevent hallucinations
    if is_social and (not title or title.lower() in ["youtube", "instagram", "login • instagram"]):
        return {"summary": "Failed to generate & extract info, please edit manually (by edit button card)", "category": "Others"}
    
    # prompt = f'''
    # You are an AI assistant for a Social Saver bot.
    # Analyze the following content or URL:
    # URL: {url}
    # Content: {text}
    
    # 1. Write a 1-sentence summary (max 15 words) of the content.
    # 2. Suggest a single Category Tag based on the content ,url and 1-sentence summary you've generated (e.g., Fitness, Coding, AI, Machine learning, Math, Food, Travel, Design, Courses, Humor, Fashion etc).
    
    # Return EXACTLY a JSON object with keys "summary" and "category". Note: ONLY RETURN JSON.
    # '''
    prompt = f'''
    You are an expert Content Classifier and AI assistant for a "Social Saver" application. 
    Your goal is to extract the core essence of the provided data and map it to the most relevant professional or lifestyle category.
    Analyze the following content or URL:
    INPUT DATA :
    URL: {url}
    Content Snippet: {text}

    INSTRUCTIONS:
    1. ANALYZE: Review the URL structure (e.g., "github.com" implies Coding, Tech or Learning Platform "medium.com/@fitness" implies Health, Fitness or Lifestyle, etc) and the keywords in the text.
    2. SUMMARIZE: Create a 1-sentence summary (max 15 words) focusing on the "Action" or "Main Value" of the content.
    3. CATEGORIZE: Select the SINGLE most accurate category. 
       - If the URL and text provide NO clear info (e.g. content is restricted, hidden, or ambiguous), do NOT guess. Set summary to "Failed to generate extract info, please edit manually (by edit button card)" and category to "Others".
       - If technical, be specific (e.g. "Machine Learning" instead of "Tech").
       - Use common industry tags: [Coding, AI, Machine Learning, Fitness, Math, Food, Travel, Design, Finance, Career, Courses, Productivity, Fashion, Humor, Business , Entertainment, Sports, Health, Education, Technology, Science, News, Politics, World Other].
       - If none fit, create a concise 1-2 word tag that represents the primary niche.

    OUTPUT FORMAT:
    Return ONLY a JSON object. No prose, no markdown blocks.
    
    EXAMPLE:
    {{
        "summary": "A comprehensive guide on building neural networks using Python and TensorFlow.",
        "category": "Machine Learning"
    }}

    CONSOLIDATED JSON RESULT:
    '''
    
    models_to_try = [
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-flash-latest"
    ]
    
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
    
    last_error = ""
    for model_name in models_to_try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                text_resp = result['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Cleaning up potential markdown formatting and grab only JSON
                start = text_resp.find('{')
                end = text_resp.rfind('}')
                if start != -1 and end != -1:
                    clean_json = text_resp[start:end+1]
                    data = json.loads(clean_json)
                    return data
                else:
                    print(f"Failed to isolate JSON. Raw text: {text_resp}")
                    return {"summary": text_resp[:60] + "...", "category": "Uncategorized"}
            else:
                last_error = f"{model_name} Error {response.status_code}: {response.text}"
                print(f"DEBUG: {last_error}")
        except Exception as e:
            print(f"Error calling {model_name}: {e}")
            
    print(f"All models failed. Last error: {last_error}")
    return {"summary": "Failed to generate & extract info, please edit manually (by edit button card)", "category": "Others"}

if __name__ == "__main__":
    res = categorize_and_summarize("Test content", "https://instagram.com/p/123")
    print("FINAL RESULT:", res)
