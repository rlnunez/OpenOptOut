"""
Admin: the community's address list for residents-only sign-up
(core/resident_addresses.py). Who may change it: users.registration.
Counts only; addresses never leave the server except as the admin's own
check of one address.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import resident_addresses as R
from ..core.access import require_permission
from ..models.database import ResidentAddress, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resident-addresses", tags=["registration"])
gate = Depends(require_permission("users.registration"))


class CheckIn(BaseModel):
    street: str
    unit: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    zip: str


@router.get("", dependencies=[gate])
def get_summary(db: Session = Depends(get_db)):
    return R.summary(db)


@router.get("/example.csv", dependencies=[gate])
def example_csv():
    return PlainTextResponse(R.EXAMPLE_CSV, media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="addresses-example.csv"'})


@router.post("/upload", dependencies=[gate])
async def upload(file: UploadFile = File(...), replace: bool = Form(True), db: Session = Depends(get_db)):
    data = await file.read(R.MAX_BYTES + 1)
    try:
        rows, problems = R.read_csv(data)
    except R.AddressError as e:
        logger.warning("Address CSV read failed: %s", e)
        safe_messages = {
            "The file is too big. Split it into files under 30 MB.",
            "The file is empty.",
        }
        msg = str(e)
        detail = msg if msg in safe_messages or msg.startswith("Couldn't find the address columns") or msg.startswith("The file has more than") else "Invalid address CSV format."
        raise HTTPException(400, detail)
    if not rows:
        raise HTTPException(400, "No usable addresses were found in the file.")
    out = R.import_rows(db, rows, replace=replace)
    return {**out, "skipped": len(problems), "problems": problems[:50], "summary": R.summary(db)}


@router.post("/check", dependencies=[gate])
def check(req: CheckIn, db: Session = Depends(get_db)):
    """Try one address the way the sign-up page will."""
    try:
        c = R.clean(req.street, req.unit or "", req.city or "", req.state or "", req.zip)
    except R.AddressError as e:
        logger.info("Address check validation failed: %s", e)
        safe_messages = {
            "Start the street address with the house or building number.",
            "Add the street name after the number.",
            "Add the 5-digit ZIP code.",
            "The address is empty.",
        }
        msg = str(e)
        return {"status": "unclear", "message": msg if msg in safe_messages else "Please check your street address and ZIP code."}
    status, row = R.match(db, c)
    return {"status": status, "cleaned": R.one_line(c),
            "accounts": R.accounts_at(db, R.keys(c)[0]) if status == "ok" else 0,
            "branch": row.branch_code if row else None}


@router.delete("", dependencies=[gate])
def clear(db: Session = Depends(get_db)):
    """Remove the whole list. Accounts stay; with the check on, nobody new can sign up."""
    n = db.query(ResidentAddress).delete()
    db.commit()
    return {"removed": n}
