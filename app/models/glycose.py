"""
Glucose log ORM model.
Represents a single glucose reading.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base


class GlucoseLog(Base):
    """Glucose log model."""
    __tablename__ = "glucose_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Glucose data
    value = Column(Float, nullable=False)  # mg/dL
    source = Column(String(50), default="cgm")  # cgm, meter, manual
    
    # Timestamps
    reading_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<GlucoseLog(id={self.id}, value={self.value}, source={self.source})>"