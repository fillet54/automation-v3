import re

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import ModelBase


class Requirement(ModelBase):
    __tablename__ = "Requirement"

    id: Mapped[str] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(1024))
    subsystem: Mapped[str] = mapped_column(String(20))

    @classmethod
    def find_by_id(cls, session, id):
        return session.query(cls).filter_by(id=id).first()

    def __eq__(self, other):
        return (self.id, self.text, self.subsystem) == (
            other.id,
            other.text,
            other.subsystem,
        )

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"<Requirement: id={self.id}>"

    def __repr_html__(self):
        if self.text:
            markup = re.sub(
                r"\s+shall\s+", f" <strong>shall [{self.id}]</strong> ", self.text
            )
        else:
            markup = f"<strong>[{self.id}]</strong>"
        return f'<div class="mb-2">{markup}</div>'
