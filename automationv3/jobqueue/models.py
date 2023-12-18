from datetime import datetime

from sqlalchemy import String, Integer, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import ModelBase


class Job:
    @property
    def title(self):
        return "??????"


class Worker(ModelBase):
    __tablename__ = "worker"

    ALLOWED_STATUS = ["available", "busy", "missing"]

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="available"
    )  # e.g., 'available', 'busy', etc.
    last_keepalive: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self):
        return f"<Worker {self.name}>"
