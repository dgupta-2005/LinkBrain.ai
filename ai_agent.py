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
       - If the content is technical, be specific (e.g. use "Machine Learning" or "Data Science" or "Web Development" or "Blockchain" or "Cyber Security" or "Cloud Computing" or "AI" or "ML" or "Deep Learning" or "Computer Vision" or "NLP" or "Robotics" or "GenAI" or "LLM" etc instead of just "Tech").
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
    return {"summary": "Gemini API Error. See logs.", "category": "Uncategorized"}

if __name__ == "__main__":
    res = categorize_and_summarize("Test content", "https://instagram.com/p/123")
    print("FINAL RESULT:", res)
