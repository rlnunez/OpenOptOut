"""
Broker data sharing and aggregator-first targeting. See core/broker_network.py.

  GET /api/broker-network/sharing      who passed opt-out addresses to whom
  GET /api/broker-network/aggregators  brokers ranked by how many others they feed
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..core.access import require_permission
from ..core.settings_store import load_settings
from ..core import broker_network as bn

router = APIRouter(prefix="/api/broker-network", tags=["broker-network"])
_admin = require_permission("brokers.manage")


@router.get("/sharing")
def sharing(db: Session = Depends(get_db), _=Depends(_admin)):
    edges = bn.sharing_edges(db)
    return {"edges": edges,
            "counts": {k: sum(1 for e in edges if e["confidence"] == k)
                       for k in ("strong", "likely", "possible", "unknown_sender")}}


@router.get("/aggregators")
def aggregators(db: Session = Depends(get_db), _=Depends(_admin)):
    order = load_settings().get("scheduler", {}).get("dispatch_order", "aggregators_first")
    return {"ranking": bn.ranking(db), "dispatch_order": order}
