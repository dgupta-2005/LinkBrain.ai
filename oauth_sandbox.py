import os
from dotenv import load_dotenv
import secrets
import hashlib
import base64
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import webbrowser
import json
import urllib.request

load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080"
SCOPE = "openid profile email"  

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET in .env file!")

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
auth_code = None

def generate_pkce_pair():
    code_verifier=secrets.token_urlsafe(64)
    sha256_has= hashlib.sha256(code_verifier.encode()).digest()
    code_challange  = base64.urlsafe_b64encode(sha256_has).decode('utf-8').replace('=', '')

    return code_verifier, code_challange

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code

        if self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        if 'code' in query_params:
            auth_code = query_params['code'][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization Successful!</h1><p>Check the terminal.</p>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Failed to capture code.")
def redirect_user_to_google(client_id, redirect_uri, scope, code_challenge, state):
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",            # Tells Google we want an Auth Code back
        "scope": scope,                     # Permissions requested (email, profile)
        "state": state,                     # CSRF prevention token
        "code_challenge": code_challenge,   # Our PKCE public hash
        "code_challenge_method": "S256",    # Hash algorithm used
        "access_type": "offline",           # Requests a refresh token
        "prompt": "consent"                 # Force screen to show every time for testing
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"
    webbrowser.open(auth_url)

def exchange_code_for_tokens(client_id, client_secret, auth_code, redirect_uri, code_verifier):
    token_endpoint = "https://oauth2.googleapis.com/token"
    
    # 1. Build POST body payload
    payload_data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,               # The temporary code caught in Step 2
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier   # Revealing the original raw PKCE secret!
    }).encode('utf-8')
    
    # 2. Prepare HTTP POST request
    req = urllib.request.Request(token_endpoint, data=payload_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    # 3. Execute request and parse response
    with urllib.request.urlopen(req) as response:
        response_body = response.read().decode('utf-8')
        tokens = json.loads(response_body)
        return tokens

def decode_id_token(id_token_string):
    # 1. Split JWT into its 3 distinct parts
    parts = id_token_string.split('.')
    payload_b64 = parts[1]
    
    # 2. Add Base64 padding if missing
    payload_b64 += '=' * (-len(payload_b64) % 4)
    
    # 3. Base64 decode into raw JSON text
    decoded_bytes = base64.b64decode(payload_b64)
    user_payload = json.loads(decoded_bytes.decode('utf-8'))
    
    return user_payload

def run_oauth_sandbox():
    print(" [Step 1] Generating PKCE Challenge...")
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    print(" [Step 2] Opening Browser for Google Login...")
    redirect_user_to_google(CLIENT_ID, REDIRECT_URI, SCOPE, code_challenge, state)

    print(" [Step 3] Waiting for Google redirect at http://localhost:8080 ...")
    server = HTTPServer(('localhost', 8080), OAuthHandler)
    server.handle_request() # Stops and waits for the browser to hit http://localhost:8080

    if auth_code:
        print(f" [Step 4] Authorization Code Captured: {auth_code[:20]}...")
        
        print(" [Step 5] Exchanging Auth Code & Code Verifier for Access Token...")
        tokens = exchange_code_for_tokens(CLIENT_ID, CLIENT_SECRET, auth_code, REDIRECT_URI, code_verifier)
        
        print("\n--- RAW TOKENS FROM GOOGLE ---")
        print(json.dumps(tokens, indent=2))

        if "id_token" in tokens:
            user_data = decode_id_token(tokens["id_token"])
            print("\n --- USER PROFILE FROM ID TOKEN ---")
            print(f"Name  : {user_data.get('name')}")
            print(f"Email : {user_data.get('email')}")

if __name__ == "__main__":
    run_oauth_sandbox()

       
