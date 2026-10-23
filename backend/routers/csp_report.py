"""
Content-Security-Policy violation reports (ASVS 3.4.7).

Browsers POST here on their own, with no auth header, whenever a response's
CSP blocks something — both the legacy report-uri mechanism
(application/csp-report) and the newer Reporting API (application/
reports+json) land on this one path. We don't parse the body beyond a size
cap; it's only ever CSP's own violated-directive/blocked-uri/document-uri
fields, not user data, and it goes through the app's own sanitizing logger
like any other log line.
"""
import logging

from fastapi import APIRouter, Depends, Request, Response

from ..core import rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["csp"])

_MAX_REPORT_BYTES = 4096


@router.post("/csp-report", status_code=204,
             dependencies=[Depends(rate_limit.limit("csp_report", 60))])
async def csp_report(request: Request):
    try:
        body = (await request.body())[:_MAX_REPORT_BYTES].decode("utf-8", "replace")
    except Exception:
        body = ""
    if body.strip():
        logger.warning("csp_violation %s", body)
    return Response(status_code=204)
