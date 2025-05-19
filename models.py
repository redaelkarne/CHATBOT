from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(200), nullable=True)
    car_model = Column(String(100), nullable=True)
    issue_description = Column(String(500), nullable=True)
    preferred_datetime = Column(String(50), nullable=True)
    matched_operation = Column(String(500), nullable=True)  # Add this line for matched_operation
