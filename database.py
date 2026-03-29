from sqlmodel import SQLModel, create_engine
import os
from models import SavedItem, User

# 1. Load the database URL from an environment variable (e.g. Supabase or SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database_v2.db")

# 2. Configure engine arguments (SQLite needs a special thread check flag)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# 3. Create the engine dynamically
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
