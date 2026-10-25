"""
Data Rights Protocol (DRP) HTTP client.

Handles communication with Covered Businesses implementing the Data Rights
Protocol (v0.9/v1.0). Dispatches authenticated data rights requests, polls
request statuses, and discovers endpoint capabilities.

Security & Privacy Guarantees:
- Enforces SSRF and DNS-rebinding protection via assert_safe_url.
- Never logs consumer PII (identity fields, names, emails, addresses).
- Enforces strict bounded timeouts on all network calls.
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

from .schema import (
    DrpExerciseRequest,
    DrpExerciseResponse,
    DrpStatusResponse,
    DRP_VERSION,
)
from ..dns_guard import assert_safe_url, safe_dns_context

log = logging.getLogger("core.drp")


class DrpError(Exception):
    """Base exception for Data Rights Protocol interactions."""
    pass


class DrpClient:
    """Client for executing requests per the Data Rights Protocol standard."""

    def __init__(self, user_agent: Optional[str] = None, allow_local: bool = False):
        self.user_agent = user_agent or f"OpenOptOut/{DRP_VERSION} (Privacy Automation)"
        self.allow_local = allow_local

    def _make_headers(self, api_token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if api_token:
            headers["Authorization"] = f"Bearer {api_token.strip()}"
        return headers

    def _open(self, req: urllib.request.Request, timeout: float):
        """Open request, bypassing environment proxy when allow_local is enabled for tests."""
        if self.allow_local:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout)

    def exercise(
        self,
        endpoint: str,
        regime: str,
        rights: list,
        identity: Dict[str, Any],
        api_token: Optional[str] = None,
        status_callback: Optional[str] = None,
        timeout: float = 20.0,
    ) -> DrpExerciseResponse:
        """
        Submit a data rights request to a Covered Business's DRP exercise endpoint.
        """
        start_time = time.monotonic()
        # Pre-flight SSRF & DNS-rebinding security check
        assert_safe_url(endpoint, schemes=("https", "http"), allow_local=self.allow_local)

        request_obj = DrpExerciseRequest(
            regime=regime,
            exercise=rights,
            identity=identity,
            status_callback=status_callback,
        )
        payload_bytes = json.dumps(request_obj.to_dict()).encode("utf-8")
        headers = self._make_headers(api_token)

        # Normalize URL: if base endpoint given without action, post to /exercise or directly to endpoint
        target_url = endpoint
        if not target_url.endswith("/exercise") and not target_url.endswith("/requests"):
            target_url = f"{target_url.rstrip('/')}/exercise"

        req = urllib.request.Request(target_url, data=payload_bytes, headers=headers, method="POST")

        log.info("Dispatching DRP exercise to %s (regime=%s, rights=%s)", target_url, regime, rights)

        try:
            with safe_dns_context(allow_local=self.allow_local):
                with self._open(req, timeout=timeout) as resp:
                    status_code = resp.status
                    body_text = resp.read().decode("utf-8")
                    data = json.loads(body_text) if body_text else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            log.warning("DRP exercise HTTP %s from %s: %s", e.code, target_url, error_body[:200])
            try:
                err_json = json.loads(error_body)
                err_msg = err_json.get("message") or err_json.get("reason") or str(e)
            except Exception:
                err_msg = f"HTTP {e.code}: {e.reason}"
            return DrpExerciseResponse(
                ok=False,
                error=err_msg,
                raw_response={"status_code": e.code, "error_body": error_body},
            )
        except Exception as e:
            log.error("DRP exercise failed for %s: %s", target_url, e)
            return DrpExerciseResponse(ok=False, error=str(e))

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        request_id = str(data.get("request_id") or data.get("id") or "")
        status_val = str(data.get("status") or "in_progress")
        reason = str(data.get("reason") or "")
        expected_by = str(data.get("expected_by") or "")
        action_url = str(data.get("user_action_url") or "")

        log.info(
            "DRP exercise accepted by %s in %dms: request_id=%s, status=%s",
            target_url, elapsed_ms, request_id, status_val,
        )

        return DrpExerciseResponse(
            ok=True,
            request_id=request_id,
            status=status_val,
            received_at=str(data.get("received_at") or ""),
            expected_by=expected_by,
            reason=reason,
            user_action_url=action_url,
            raw_response=data,
        )

    def check_status(
        self,
        endpoint: str,
        request_id: str,
        api_token: Optional[str] = None,
        timeout: float = 15.0,
    ) -> DrpStatusResponse:
        """
        Query the current status of an in-flight or completed DRP request.
        """
        assert_safe_url(endpoint, schemes=("https", "http"), allow_local=self.allow_local)

        base = endpoint.rstrip("/")
        if base.endswith("/exercise"):
            base = base[:-9]
        
        # Check standard DRP status URL patterns
        status_url = f"{base}/status/{urllib.parse.quote(request_id)}"
        headers = self._make_headers(api_token)
        req = urllib.request.Request(status_url, headers=headers, method="GET")

        try:
            with safe_dns_context(allow_local=self.allow_local):
                with self._open(req, timeout=timeout) as resp:
                    body_text = resp.read().decode("utf-8")
                    data = json.loads(body_text) if body_text else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            return DrpStatusResponse(ok=False, request_id=request_id, error=f"HTTP {e.code}: {error_body[:200]}")
        except Exception as e:
            return DrpStatusResponse(ok=False, request_id=request_id, error=str(e))

        return DrpStatusResponse(
            ok=True,
            request_id=str(data.get("request_id") or request_id),
            status=str(data.get("status") or "in_progress"),
            reason=str(data.get("reason") or ""),
            updated_at=str(data.get("updated_at") or ""),
            raw_response=data,
        )

    def discover(self, base_url: str, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Discover a Covered Business's DRP capabilities from its well-known endpoint.
        """
        assert_safe_url(base_url, schemes=("https", "http"), allow_local=self.allow_local)
        well_known_url = f"{base_url.rstrip('/')}/.well-known/data-rights"
        headers = self._make_headers()
        req = urllib.request.Request(well_known_url, headers=headers, method="GET")

        try:
            with safe_dns_context(allow_local=self.allow_local):
                with self._open(req, timeout=timeout) as resp:
                    body_text = resp.read().decode("utf-8")
                    return json.loads(body_text) if body_text else {}
        except Exception as e:
            log.debug("DRP discovery failed at %s: %s", well_known_url, e)
            return {}
