import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Enum
from app.core.database import Base

class DocumentType(str, enum.Enum):
    DEATH_CERTIFICATE = "death_certificate"
    MEDICAL_RECORD = "medical_record"
    IDENTIFICATION = "identification"
    OTHER = "other"

class DocumentStore(Base):
    __tablename__ = "document_store"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    document_type = Column(Enum(DocumentType), nullable=True)
    file_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
