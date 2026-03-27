from sqlmodel import SQLModel, create_engine
import os
from models import SavedItem, User

sqlite_file_name = "database_v2.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
