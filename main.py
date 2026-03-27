import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import engine, create_db_and_tables
from models import SavedItem, User, CustomBucket
from bot import start_bot
from auth import verify_password, get_password_hash, create_access_token, decode_access_token
from datetime import timedelta

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables and start background bot
    create_db_and_tables()
    bot_task = asyncio.create_task(start_bot())
    yield
    # Shutdown
    bot_task.cancel()

app = FastAPI(lifespan=lifespan)
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

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": error})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user or not verify_password(password, user.hashed_password):
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
        # Ensuring the item belongs to the logged-in user before deleting
        if item and item.user_id == user.id:
            session.delete(item)
            session.commit()
            
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
