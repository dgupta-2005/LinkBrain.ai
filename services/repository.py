from typing import Generic, TypeVar, Type, Optional, List
from sqlmodel import Session, select, SQLModel
from database import engine
from models import User, SavedItem, CustomBucket

T = TypeVar("T", bound=SQLModel)

class DatabaseRepository(Generic[T]):
    """Generic Base Repository encapsulating fundamental CRUD operations."""

    def __init__(self, model_cls: Type[T]):
        self.model_cls = model_cls

    def get_by_id(self, item_id: int) -> Optional[T]:
        with Session(engine) as session:
            return session.get(self.model_cls, item_id)

    def add(self, entity: T) -> T:
        with Session(engine) as session:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity

    def delete(self, item_id: int, user_id: int) -> bool:
        with Session(engine) as session:
            item = session.get(self.model_cls, item_id)
            if item and getattr(item, "user_id", None) == user_id:
                session.delete(item)
                session.commit()
                return True
            return False


class UserRepository(DatabaseRepository[User]):
    """Specialized repository for User domain operations."""

    def __init__(self):
        super().__init__(User)

    def get_by_username(self, username: str) -> Optional[User]:
        with Session(engine) as session:
            return session.exec(select(User).where(User.username == username)).first()

    def get_by_telegram_chat_id(self, chat_id: str) -> Optional[User]:
        with Session(engine) as session:
            return session.exec(select(User).where(User.telegram_chat_id == str(chat_id))).first()

    def get_by_link_token(self, token: str) -> Optional[User]:
        with Session(engine) as session:
            return session.exec(select(User).where(User.link_token == token)).first()


class ItemRepository(DatabaseRepository[SavedItem]):
    """Specialized repository for SavedItem operations."""

    def __init__(self):
        super().__init__(SavedItem)

    def get_all_for_user(self, user_id: int) -> List[SavedItem]:
        with Session(engine) as session:
            return session.exec(select(SavedItem).where(SavedItem.user_id == user_id)).all()

    def update_item(self, item_id: int, user_id: int, summary: str, category: str) -> Optional[SavedItem]:
        with Session(engine) as session:
            item = session.get(SavedItem, item_id)
            if item and item.user_id == user_id:
                item.summary = summary.strip()
                item.category = category.strip()
                session.add(item)
                session.commit()
                session.refresh(item)
                return item
            return None


class BucketRepository(DatabaseRepository[CustomBucket]):
    """Specialized repository for CustomBucket operations."""

    def __init__(self):
        super().__init__(CustomBucket)

    def get_all_for_user(self, user_id: int) -> List[CustomBucket]:
        with Session(engine) as session:
            return session.exec(select(CustomBucket).where(CustomBucket.user_id == user_id)).all()