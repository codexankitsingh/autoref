import base64
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models.message import Message

router = APIRouter(prefix="/api/track", tags=["tracking"])

# A minimal 1x1 transparent PNG image
TRANSPARENT_PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@router.get("/open/{tracking_id}")
def track_open(tracking_id: str, request: Request, db: Session = Depends(get_db)):
    """Tracking pixel endpoint. Returns 1x1 transparent PNG."""
    msg = db.query(Message).filter(Message.tracking_id == tracking_id).first()
    
    if msg:
        msg.open_count = (msg.open_count or 0) + 1
        if not msg.opened_at:
            msg.opened_at = datetime.utcnow()
        msg.last_opened_at = datetime.utcnow()
        
        # We don't change the overall thread status based on opens to avoid overriding
        # manual status like "interview_scheduled" or "replied".
        
        db.commit()
    
    return Response(content=TRANSPARENT_PIXEL, media_type="image/png")
