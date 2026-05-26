import base64
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models.message import Message

router = APIRouter(prefix="/api/track", tags=["tracking"])

# A minimal 1x1 transparent PNG image
TRANSPARENT_PIXEL = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

# Known bot/scanner User-Agent substrings.
# Gmail, Outlook, and corporate security gateways pre-fetch links to scan for
# malware. These automated fetches trigger our tracking endpoint and inflate
# click counts with false positives.
BOT_SIGNATURES = [
    "googlebot", "google-safety", "google-extended",
    "bingpreview", "bingbot",
    "outlook", "microsoft office", "ms-office",
    "barracuda",        # Barracuda email security gateway
    "mimecast",         # Mimecast email security
    "proofpoint",       # Proofpoint URL defense
    "symantec",         # Symantec email security
    "messagelabs",      # Symantec MessageLabs
    "slurp",            # Yahoo
    "facebookexternalhit",
    "twitterbot",
    "linkedinbot",
    "whatsapp",
    "bot", "crawler", "spider", "fetcher", "preview",
    "headlesschrome",   # Headless browsers used by security scanners
]


def _is_bot(request: Request) -> bool:
    """Check if the request comes from a known bot or link scanner."""
    ua = (request.headers.get("user-agent") or "").lower()
    if not ua:
        return True  # No user-agent = almost certainly a scanner
    return any(sig in ua for sig in BOT_SIGNATURES)


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

@router.get("/click/{tracking_id}")
def track_click(tracking_id: str, url: str, request: Request, db: Session = Depends(get_db)):
    """
    Tracking link click endpoint. Redirects to the actual URL.
    Filters out bot/scanner traffic to prevent inflated click counts.
    """
    if not url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    msg = db.query(Message).filter(Message.tracking_id == tracking_id).first()
    
    # Only count clicks from real humans, not email security scanners
    if msg and not _is_bot(request):
        msg.click_count = (msg.click_count or 0) + 1
        msg.last_clicked_at = datetime.utcnow()
        db.commit()
    
    return RedirectResponse(url=url, status_code=302)
