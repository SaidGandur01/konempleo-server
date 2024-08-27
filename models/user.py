from enum import IntEnum
from sqlalchemy import TIMESTAMP, Boolean, Column, Enum, Integer, String

from db.base_class import Base

class UserEnum(IntEnum):
    super_admin = 1
    admin = 2
    company = 3

class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    fullname = Column(String, nullable=False)
    email = Column(String, nullable=False)
    role = Column(Enum(UserEnum), nullable=False)
    active = Column(Boolean, default=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
    must_change_password = Column(Boolean, default=True)
