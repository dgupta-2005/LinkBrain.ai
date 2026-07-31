import os
from sqlmodel import SQLModel, create_engine
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database_v2.db").strip()
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Singleton Engine Instance
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)