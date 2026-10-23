"""
Shared Content-Security-Policy strings for the handful of places this
backend returns an HTML or SVG document directly (everything else is JSON
via FastAPI, or the separately-configured frontend SPA/nginx/Caddy policy —
see SECURITY.md's "Web Frontend & Browser Security" section). Kept in one
place so a change here (like adding the report-uri below) only has to
happen once instead of being copy-pasted per route.
"""

CSP_REPORT_PATH = "/api/csp-report"

# ASVS 3.4.3: object-src/base-uri 'none'. ASVS 3.4.7: violations are reported
# via both the legacy report-uri directive and the newer Reporting API.
MINIMAL_HTML_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
    f"object-src 'none'; base-uri 'none'; report-uri {CSP_REPORT_PATH}; report-to csp-endpoint;"
)
SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
REPORTING_ENDPOINTS_HEADER = f'csp-endpoint="{CSP_REPORT_PATH}"'
