import os
import json
import requests
from dotenv import load_dotenv
load_dotenv()
def categorize_and_summarize(text: str, url: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"summary": "Gemini API Key missing.", "category": "Uncategorized"}
        
    try:
        res = requests.get(f"https://api.microlink.io?url={url}", timeout=5)
        if res.status_code == 200:
            microlink_data = res.json().get('data', {})
            title = microlink_data.get('title', '')
            desc = microlink_data.get('description', '')
            if title or desc:
                text = f"{text}\n\n[Extracted Web Data]\nTitle: {title}\nDescription: {desc}"
    except Exception as e:
        print(f"Microlink extraction failed: {e}")
    
    prompt = f'''
    You are an AI assistant for a Social Saver bot.
    Analyze the following content or URL:
    URL: {url}
    Content: {text}
    
    1. Write a 1-sentence summary (max 15 words) of the content.
    2. Suggest a single Category Tag (e.g., Fitness, Coding, Food, Travel, Design, Humor).
    
    Return EXACTLY a JSON object with keys "summary" and "category". Note: ONLY RETURN JSON.
    '''
    
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest"
    ]
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    last_error = ""
    for model_name in models_to_try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                text_resp = result['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Clean up potential markdown formatting and grab only JSON
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
                last_error = f"{model_name} failed: {response.text}"
                print(last_error)
        except Exception as e:
            print(f"Error calling {model_name}: {e}")
            
    print(f"All models failed. Last error: {last_error}")
    return {"summary": "Gemini API Error. See logs.", "category": "Uncategorized"}

if __name__ == "__main__":
    res = categorize_and_summarize("Test content", "https://instagram.com/p/123")
    print("FINAL RESULT:", res)
