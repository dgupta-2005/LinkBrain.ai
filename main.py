import os
import asyncio
import json
import base64
import secrets
import hashlib
import hmac
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import timedelta, datetime

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import engine, create_db_and_tables
from models import SavedItem, User, CustomBucket
from bot import start_bot
from auth import verify_password, get_password_hash, create_access_token, decode_access_token

load_dotenv(override=True)

# Google OAuth Credentials & Dynamic Redirect URI
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Dynamically sets domain based on Render environment or defaults to localhost
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000").rstrip("/")
GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/google/callback"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start background bot
    create_db_and_tables()
    
    bot_task = None
    if os.getenv("START_BOT", "true").lower() == "true":
        bot_task = asyncio.create_task(start_bot())
    else:
        print("Telegram bot startup skipped (START_BOT=false)")
        
    yield
    # Shutdown
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
    payload = decode_access_token(token)
    if not payload:
        return None 
    username = payload.get("sub")
    if not username:
        return None
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        return user


# Helper function ported from oauth_sandbox.py to decode Google ID Token (JWT)
def decode_id_token(id_token_string: str) -> dict:
    parts = id_token_string.split('.')
    payload_b64 = parts[1]
    payload_b64 += '=' * (-len(payload_b64) % 4)
    decoded_bytes = base64.b64decode(payload_b64)
    return json.loads(decoded_bytes.decode('utf-8'))


# ==========================================
# AUTHENTICATION ROUTES (LOGIN / REGISTER / GOOGLE OAUTH)
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": error})


@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        
        # Safeguard: check user existence and ensure hashed_password exists before verifying
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            return RedirectResponse(url="/login?error=Invalid username or password", status_code=status.HTTP_303_SEE_OTHER)
        
        access_token_expires = timedelta(minutes=60*24*7)
        access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
        
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, max_age=60*24*7*60)
        return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="register.html", context={"request": request, "error": error})


@app.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user:
            return RedirectResponse(url="/register?error=Username already exists", status_code=status.HTTP_303_SEE_OTHER)
        
        hashed = get_password_hash(password)
        new_user = User(username=username, hashed_password=hashed)
        session.add(new_user)
        session.commit()
    return RedirectResponse(url="/login?error=Registration successful! Please login.", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response


# ----------------------------------------------------
# 🚀 GOOGLE OAUTH ROUTES
# ----------------------------------------------------

@app.get("/auth/google/login")
async def login_google():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google Client credentials missing in environment variables")

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
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"
    return RedirectResponse(url=google_auth_url)


@app.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str = None):
    if not code:
        return RedirectResponse(url="/login?error=Authorization code missing from Google")

    # 1. Exchange Auth Code for Tokens
    token_endpoint = "https://oauth2.googleapis.com/token"
    payload_data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URI
    }).encode('utf-8')

    req = urllib.request.Request(token_endpoint, data=payload_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as response:
            response_body = response.read().decode('utf-8')
            tokens = json.loads(response_body)
    except Exception as e:
        print(f"Error exchanging token: {e}")
        return RedirectResponse(url="/login?error=Failed to exchange code with Google")

    id_token = tokens.get("id_token")
    if not id_token:
        return RedirectResponse(url="/login?error=Google did not return id_token")

    # 2. Decode ID Token payload to extract email
    user_data = decode_id_token(id_token)
    email = user_data.get("email")

    if not email:
        return RedirectResponse(url="/login?error=Could not retrieve email from Google")

    # 3. Fetch or Create User in DB
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == email)).first()

        if not user:
            random_password = secrets.token_hex(16)
            hashed_pwd = get_password_hash(random_password)
            user = User(username=email, hashed_password=hashed_pwd)
            session.add(user)
            session.commit()
            session.refresh(user)

        # 4. Set Session Cookie and Redirect to Dashboard
        access_token_expires = timedelta(minutes=60 * 24 * 7)
        app_jwt = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)

        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {app_jwt}",
            httponly=True,
            max_age=60 * 24 * 7 * 60
        )
        return response


# ==========================================
# DASHBOARD & ITEM MANAGEMENT ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, q: str = "", platform: str = "", order: str = "newest"):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    with Session(engine) as session:
        statement = select(SavedItem).where(SavedItem.user_id == user.id)
        
        custom_buckets = session.exec(select(CustomBucket).where(CustomBucket.user_id == user.id)).all()
        custom_platform_names = [cb.platform for cb in custom_buckets]
        
        from collections import Counter
        all_user_items = session.exec(select(SavedItem).where(SavedItem.user_id == user.id)).all()
        counts = Counter(item.platform for item in all_user_items)
        
        excluded_platforms = {'Instagram', 'Twitter', 'X', 'YouTube'} | set(custom_platform_names)
        bucket_counts = {
            'All Links': sum(counts.values()),
            'Instagram': counts.get('Instagram', 0),
            'Twitter / X': counts.get('Twitter', 0) + counts.get('X', 0),
            'YouTube': counts.get('YouTube', 0),
            'Others': sum(count for plat, count in counts.items() if plat not in excluded_platforms)
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
                for custom_plat in custom_platform_names:
                    statement = statement.where(SavedItem.platform != custom_plat)
            else:
                statement = statement.where(SavedItem.platform == platform)
                
        if order == "oldest":
            statement = statement.order_by(SavedItem.created_at.asc())
        else:
            statement = statement.order_by(SavedItem.created_at.desc())
            
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
        with Session(engine) as session:
            existing = session.exec(
                select(CustomBucket).where(
                    (CustomBucket.user_id == user.id) & 
                    (CustomBucket.platform == platform_name)
                )
            ).first()
            if not existing:
                new_bucket = CustomBucket(platform=platform_name, user_id=user.id)
                session.add(new_bucket)
                session.commit()
            
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    with Session(engine) as session:
        item = session.get(SavedItem, item_id)
        if item and item.user_id == user.id:
            session.delete(item)
            session.commit()
            
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/edit/{item_id}")
async def edit_item(
    request: Request, 
    item_id: int, 
    summary: str = Form(...), 
    category: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    with Session(engine) as session:
        item = session.get(SavedItem, item_id)
        if item and item.user_id == user.id:
            item.summary = summary.strip()
            item.category = category.strip()
            session.add(item)
            session.commit()
            
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# TELEGRAM BOT INTEGRATION ENDPOINTS
# ==========================================

@app.post("/api/telegram/generate-link-url")
def generate_telegram_link_url(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Authentication required."
        )

    with Session(engine) as session:
        db_user = session.get(User, user.id)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Generate a single-use token valid for 10 minutes
        token = f"connect_{secrets.token_urlsafe(16)}"
        db_user.link_token = token
        db_user.link_token_expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        session.add(db_user)
        session.commit()

        bot_username = "bunny05_bot"  
        telegram_url = f"https://t.me/{bot_username}?start={token}"

        return {"telegram_url": telegram_url}