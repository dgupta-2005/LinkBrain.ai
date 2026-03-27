from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from typing import Optional, List
import uuid

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    telegram_chat_id: Optional[str] = Field(default=None, index=True)
    link_code: str = Field(default_factory=lambda: str(uuid.uuid4())[:6].upper(), unique=True)
    
    saved_items: List["SavedItem"] = Relationship(back_populates="user")
    custom_buckets: List["CustomBucket"] = Relationship(back_populates="user")

class SavedItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str
    platform: str = Field(default="Unknown")
    summary: str = Field(default="")
    category: str = Field(default="Uncategorized")
    raw_text: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="saved_items")

class CustomBucket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user: Optional[User] = Relationship(back_populates="custom_buckets")
