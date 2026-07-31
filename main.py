import os
import requests
import asyncio
import secrets
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import timedelta, datetime

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import engine, create_db_and_tables
from models import SavedItem, User, CustomBucket
from bot import start_bot
from services import UserRepository, ItemRepository, BucketRepository, AuthService

load_dotenv(override=True)

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
# Dynamically detect environment: Production (Render) vs Localhost
IS_RENDER = os.getenv("RENDER") == "true"

if IS_RENDER:
    BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://linkbrain-ai-aaih.onrender.com").rstrip("/")
else:
    BASE_URL = "http://localhost:8000"

GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/google/callback"

user_repo = UserRepository()
item_repo = ItemRepository()
bucket_repo = BucketRepository()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    bot_task = None
    if os.getenv("START_BOT", "true").lower() == "true":
        bot_task = asyncio.create_task(start_bot())
    yield
    if bot_task:
        bot_task.cancel()

app = FastAPI(lifespan=lifespan)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
templates = Jinja2Templates(directory="templates")

def get_current_user(request: Request) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    if token.startswith("Bearer "):
        token = token.split(" ")[1]
    payload = AuthService.decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    return user_repo.get_by_username(payload["sub"])

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "LinkBrain server is awake!"}

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": error})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = user_repo.get_by_username(username)
    if not user or not user.hashed_password or not AuthService.verify_password(password, user.hashed_password):
        return RedirectResponse(url="/login?error=Invalid username or password", status_code=status.HTTP_303_SEE_OTHER)

    access_token = AuthService.create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, max_age=60*24*7*60)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="register.html", context={"request": request, "error": error})

@app.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if user_repo.get_by_username(username):
        return RedirectResponse(url="/register?error=Username already exists", status_code=status.HTTP_303_SEE_OTHER)

    hashed = AuthService.get_password_hash(password)
    new_user = User(username=username, hashed_password=hashed)
    user_repo.add(new_user)
    return RedirectResponse(url="/login?error=Registration successful! Please login.", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response

# ==========================================
# GOOGLE OAUTH ROUTES
# ==========================================

@app.get("/auth/google/login")
async def login_google():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google Client credentials missing")

    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}")

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str = None):
    if not code:
        return RedirectResponse(url="/login?error=Authorization code missing from Google")

    # 1. Exchange Auth Code for Tokens using 'requests'
    token_endpoint = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URI
    }

    try:
        token_res = requests.post(token_endpoint, data=payload, timeout=10)
        
        # If Google rejects the code, log the exact error message to terminal
        if token_res.status_code != 200:
            print(f"❌ Google Token Exchange Error ({token_res.status_code}): {token_res.text}")
            return RedirectResponse(url="/login?error=Failed to exchange code with Google")
        
        tokens = token_res.json()
    except Exception as e:
        print(f"❌ Network Exception during Google token exchange: {e}")
        return RedirectResponse(url="/login?error=Failed to exchange code with Google")

    id_token = tokens.get("id_token")
    if not id_token:
        return RedirectResponse(url="/login?error=Google did not return id_token")

    # 2. Decode ID Token payload to extract user email
    user_data = AuthService.decode_id_token(id_token)
    email = user_data.get("email")

    if not email:
        return RedirectResponse(url="/login?error=Could not retrieve email from Google")

    # 3. Fetch or Create User via Repository
    user = user_repo.get_by_username(email)
    if not user:
        random_password = secrets.token_hex(16)
        hashed_pwd = AuthService.get_password_hash(random_password)
        user = User(username=email, hashed_password=hashed_pwd)
        user = user_repo.add(user)

    # 4. Issue JWT Cookie & Redirect to Dashboard
    access_token = AuthService.create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=60 * 24 * 7 * 60
    )
    return response

# ==========================================
# DASHBOARD ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, q: str = "", platform: str = "", order: str = "newest"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    with Session(engine) as session:
        statement = select(SavedItem).where(SavedItem.user_id == user.id)
        custom_buckets = bucket_repo.get_all_for_user(user.id)
        custom_platform_names = [cb.platform for cb in custom_buckets]

        from collections import Counter
        all_user_items = item_repo.get_all_for_user(user.id)
        counts = Counter(item.platform for item in all_user_items)

        excluded = {'Instagram', 'Twitter', 'X', 'YouTube'} | set(custom_platform_names)
        bucket_counts = {
            'All Links': sum(counts.values()),
            'Instagram': counts.get('Instagram', 0),
            'Twitter / X': counts.get('Twitter', 0) + counts.get('X', 0),
            'YouTube': counts.get('YouTube', 0),
            'Others': sum(count for plat, count in counts.items() if plat not in excluded)
        }
        for plat in custom_platform_names:
            bucket_counts[plat] = counts.get(plat, 0)

        if q:
            statement = statement.where(
                (SavedItem.summary.contains(q)) | 
                (SavedItem.category.contains(q)) |
                (SavedItem.raw_text.contains(q))
            )
        if platform:
            if platform == 'Others':
                statement = statement.where(
                    (SavedItem.platform != 'Instagram') &
                    (SavedItem.platform != 'Twitter') &
                    (SavedItem.platform != 'X') &
                    (SavedItem.platform != 'YouTube')
                )
                for cp in custom_platform_names:
                    statement = statement.where(SavedItem.platform != cp)
            else:
                statement = statement.where(SavedItem.platform == platform)

        statement = statement.order_by(SavedItem.created_at.asc() if order == "oldest" else SavedItem.created_at.desc())
        items = session.exec(statement).all()

    return templates.TemplateResponse(
        request=request, name="index.html", context={"items": items, "q": q, "user": user, "current_platform": platform, "order": order, "custom_buckets": custom_buckets, "bucket_counts": bucket_counts}
    )

@app.post("/bucket/new")
async def create_custom_bucket(request: Request, platform_name: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    platform_name = platform_name.strip()
    if platform_name:
        bucket_repo.add(CustomBucket(platform=platform_name, user_id=user.id))
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    item_repo.delete(item_id, user.id)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/edit/{item_id}")
async def edit_item(request: Request, item_id: int, summary: str = Form(...), category: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    item_repo.update_item(item_id, user.id, summary, category)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/telegram/generate-link-url")
def generate_telegram_link_url(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")

    with Session(engine) as session:
        db_user = session.get(User, user.id)
        token = f"connect_{secrets.token_urlsafe(16)}"
        db_user.link_token = token
        db_user.link_token_expires_at = datetime.utcnow() + timedelta(minutes=10)
        session.add(db_user)
        session.commit()

        return {"telegram_url": f"https://t.me/bunny05_bot?start={token}"}