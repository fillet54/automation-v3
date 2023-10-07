import re

from sqlalchemy import String, select, delete
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.exc import NoResultFound

# TODO: Move to a database package
from sqlalchemy.ext import declarative
ModelBase = declarative.declarative_base()

class Requirement(ModelBase):
    __tablename__ = 'Requirement'

    id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(1024))
    subsystem: Mapped[str] = mapped_column(String(20))

    @classmethod
    def find_by_id(cls, session, id):
        return session.query(cls).filter_by(id=id).first()

    def __repr_html__(self):
        markup = re.sub(r'\s+shall\s+', f' <strong>shall [{self.id}]</strong> ', self.text)
        return f'<div class="mb-2">{markup}</div>'
