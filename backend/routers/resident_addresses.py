"""
Admin: the community's address list for residents-only sign-up
(core/resident_addresses.py). Who may change it: users.registration.
Counts only; addresses never leave the server except as the admin's own
check of one address.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core import resident_addresses as R
from ..core.access import require_permission
from ..models.database import ResidentAddress, User, get_db

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
        raise HTTPException(400, str(e))
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
        return {"status": "unclear", "message": str(e)}
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
