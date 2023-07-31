from sqlalchemy import String, select, delete
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.exc import NoResultFound

from .base import ModelBase

class Requirement(ModelBase):
    __tablename__ = 'Requirement'

    id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(1024))
    subsystem: Mapped[str] = mapped_column(String(20))

