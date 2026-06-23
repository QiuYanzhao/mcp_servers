"""数据库会话辅助。"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from .config import init_star_stocks_env

init_star_stocks_env()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    from star_stocks.database import get_session_factory

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
