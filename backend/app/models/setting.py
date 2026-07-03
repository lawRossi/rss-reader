"""Setting model for storing key-value configuration."""

from sqlalchemy import Column, String, Text
from app.database import Base


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, default="")

    def __repr__(self):
        return f"<Setting(key={self.key})>"
