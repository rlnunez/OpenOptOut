"""
A harvester's-eye test of a COUNTER API (SUSHI) service: the checks a library
system's harvester depends on. Used by the "Run the self-test" button
(Admin → Usage statistics) and by scripts/sushi-harvest-test.py, which points
it at any server.

Standard library only, and no imports from the app, so the script can load
this file on its own.

run(get, requestor_id, api_key, customer_id) -> [{"key", "ok", "detail"}]
where get(path, params) -> (http_status, parsed JSON or None), and path is
relative to the base address ("/r51/status").
"""
import re
from datetime import date

# Every check, in the reader's words (scripts/extract_page_texts.py reads this).
CHECK_TEXTS = {
    "status_public": "The service status answers without a key",
    "no_credentials": "A request without credentials is refused",
    "bad_requestor": "An unknown requestor ID is refused (2000)",
    "bad_key": "A wrong API key is refused (2020)",
    "world_refused": "Global (\"The World\") reports are refused (2011)",
    "bad_customer": "An unknown customer ID is refused (2010)",
    "members": "Members lists the institutions",
    "reports_list": "The report list includes PR and PR_P1",
    "report_shape": "{report}: header and monthly counts are in COUNTER 5.1 form",
    "bad_dates": "Dates the wrong way round are refused (3020)",
    "bad_date_format": "A date that isn't a date is refused (3020)",
    "not_ready": "The current month is reported as not ready (3031)",
    "unknown_param": "An unknown parameter is reported (3050)",
    "messages": "Error messages match the Code of Practice",
}

MESSAGES = {
    1000: "Service Not Available", 1030: "Insufficient Information to Process Request",
    2000: "Requestor Not Authorized to Access Service",
    2010: "Requestor is Not Authorized to Access Usage for Institution",
    2011: "Global Reports Not Supported", 2020: "APIKey Invalid", 3020: "Invalid Date Arguments",
    3030: "No Usage Available for Requested Dates", 3031: "Usage Not Ready for Requested Dates",
    3050: "Parameter Not Recognized in this Context", 3060: "Invalid ReportFilter Value",
    3062: "Invalid ReportAttribute Value",
}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CREATED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _add_months(d, n):
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def _code(body):
    """The exception code in an error body (an Exception object, or a list of them)."""
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        if "Code" in body:
            return body.get("Code")
        if isinstance(body.get("Exception"), dict):
            return body["Exception"].get("Code")
    return None


def _header_codes(body):
    try:
        return [e.get("Code") for e in body["Report_Header"].get("Exceptions") or []]
    except (TypeError, KeyError, AttributeError):
        return []


def check_report(body, report_id, begin, end):
    """Problems with one report body, in plain words (empty when it's fine)."""
    p = []
    if not isinstance(body, dict) or "Report_Header" not in body or "Report_Items" not in body:
        return ["not a report (needs Report_Header and Report_Items)"]
    h = body["Report_Header"]
    for k in ("Release", "Report_ID", "Report_Name", "Created", "Created_By", "Institution_Name",
              "Institution_ID", "Report_Filters"):
        if k not in h:
            p.append(f"header has no {k}")
    if h.get("Release") != "5.1":
        p.append(f"Release is {h.get('Release')!r}, not \"5.1\"")
    if h.get("Report_ID") != report_id:
        p.append(f"Report_ID is {h.get('Report_ID')!r}, expected {report_id!r}")
    if "Created" in h and not CREATED.match(str(h["Created"])):
        p.append("Created isn't an RFC 3339 date-time")
    if "Institution_ID" in h and not isinstance(h["Institution_ID"], dict):
        p.append("Institution_ID isn't an object like {\"Proprietary\": [...]}")
    f = h.get("Report_Filters") or {}
    if not isinstance(f, dict) or not f.get("Begin_Date") or not f.get("End_Date"):
        p.append("Report_Filters has no Begin_Date and End_Date")
    for e in h.get("Exceptions") or []:
        if not isinstance(e, dict) or set(e) - {"Code", "Message", "Help_URL", "Data"} or "Code" not in e:
            p.append("an exception has fields other than Code, Message, Help_URL, Data")
        elif e["Code"] in MESSAGES and e.get("Message") != MESSAGES[e["Code"]]:
            p.append(f"exception {e['Code']} message isn't the standard one")
    items = body["Report_Items"]
    if not isinstance(items, list):
        return p + ["Report_Items isn't a list"]
    if not items and 3030 not in _header_codes(body):
        p.append("no usage, but no 3030 exception in the header")
    lo, hi = f"{begin.year:04d}-{begin.month:02d}", f"{end.year:04d}-{end.month:02d}"
    for it in items:
        if not isinstance(it, dict) or "Platform" not in it or not isinstance(it.get("Attribute_Performance"), list):
            p.append("an item has no Platform or Attribute_Performance list")
            continue
        for ap in it["Attribute_Performance"]:
            if "Data_Type" not in ap or not isinstance(ap.get("Performance"), dict):
                p.append("an Attribute_Performance has no Data_Type or Performance")
                continue
            for metric, months in ap["Performance"].items():
                if not isinstance(months, dict) or not months:
                    p.append(f"{metric} has no months")
                    continue
                for m, n in months.items():
                    if not MONTH.match(m):
                        p.append(f"{metric}: {m!r} isn't yyyy-mm")
                    elif not lo <= m <= hi:
                        p.append(f"{metric}: {m} is outside the requested months")
                    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
                        p.append(f"{metric} {m}: counts must be whole numbers above 0 (zeros are left out)")
    return sorted(set(p))


def run(get, requestor_id, api_key, customer_id="all", today=None):
    today = today or date.today()
    out = []
    creds = {"requestor_id": requestor_id, "api_key": api_key, "customer_id": customer_id}

    def add(key, ok, detail="", **fmt):
        out.append({"key": key, "ok": bool(ok), "detail": detail, "vars": fmt})

    def expect_error(key, params, path, codes):
        st, body = get(path, params)
        c = _code(body)
        add(key, st >= 400 and c in codes, f"HTTP {st}, code {c}")
        return body

    st, body = get("/r51/status", {})
    add("status_public", st == 200 and isinstance(body, list) and body and "Service_Active" in body[0],
        f"HTTP {st}" + (f", Service_Active={body[0].get('Service_Active')}" if isinstance(body, list) and body else ""))
    errs = []
    errs.append(expect_error("no_credentials", {"customer_id": customer_id}, "/r51/reports", (1030, 2000, 2020)))
    errs.append(expect_error("bad_requestor", dict(creds, requestor_id="nobody-" + requestor_id), "/r51/reports", (2000,)))
    errs.append(expect_error("bad_key", dict(creds, api_key="wrong" + api_key), "/r51/reports", (2020,)))
    errs.append(expect_error("world_refused", dict(creds, customer_id="0000000000000000"), "/r51/reports", (2011, 2010)))
    errs.append(expect_error("bad_customer", dict(creds, customer_id="no-such-customer"), "/r51/reports", (2010,)))

    st, body = get("/r51/members", creds)
    ok = st == 200 and isinstance(body, list) and body and all("Customer_ID" in m and "Name" in m for m in body)
    add("members", ok, f"HTTP {st}, {len(body) if isinstance(body, list) else 0} institution(s)")

    st, body = get("/r51/reports", creds)
    ids = [r.get("Report_ID") for r in body] if isinstance(body, list) else []
    add("reports_list", st == 200 and "PR" in ids and "PR_P1" in ids
        and all(r.get("Release") == "5.1" for r in body), f"HTTP {st}: {', '.join(map(str, ids))}")

    last = _add_months(today.replace(day=1), -1)
    first = _add_months(last, -11)
    for r in (body if isinstance(body, list) else []):
        path = r.get("Path") or f"/r51/reports/{str(r.get('Report_ID', '')).lower()}"
        path = path[path.find("/r51/"):] if "/r51/" in path else path
        params = dict(creds, begin_date=f"{first:%Y-%m}", end_date=f"{last:%Y-%m}")
        if r.get("Report_ID") == "PR":
            params["attributes_to_show"] = "Access_Method"
        st, rep = get(path, params)
        problems = check_report(rep, r.get("Report_ID"), first, last) if st == 200 else [f"HTTP {st}"]
        add("report_shape", not problems, "; ".join(problems[:5]) or "OK", report=r.get("Report_ID"))

    errs.append(expect_error("bad_dates", dict(creds, begin_date=f"{last:%Y-%m}", end_date=f"{first:%Y-%m}"),
                             "/r51/reports/pr", (3020,)))
    errs.append(expect_error("bad_date_format", dict(creds, begin_date="last-year", end_date=f"{last:%Y-%m}"),
                             "/r51/reports/pr", (3020,)))
    st, rep = get("/r51/reports/pr", dict(creds, begin_date=f"{last:%Y-%m}", end_date=f"{today:%Y-%m}"))
    add("not_ready", st == 200 and 3031 in _header_codes(rep), f"HTTP {st}, exceptions {_header_codes(rep)}")
    st, rep = get("/r51/reports/pr", dict(creds, begin_date=f"{first:%Y-%m}", end_date=f"{last:%Y-%m}",
                                          favourite_colour="blue"))
    add("unknown_param", st == 200 and 3050 in _header_codes(rep), f"HTTP {st}, exceptions {_header_codes(rep)}")

    wrong = []
    for b in errs:
        if isinstance(b, list) and b:
            b = b[0]
        if isinstance(b, dict) and b.get("Code") in MESSAGES and b.get("Message") != MESSAGES[b["Code"]]:
            wrong.append(str(b.get("Code")))
    add("messages", not wrong, ("non-standard: " + ", ".join(wrong)) if wrong else "OK")
    return out


def text(result):
    """A check's label in English, with its values filled in."""
    return CHECK_TEXTS[result["key"]].format(**result.get("vars") or {})
