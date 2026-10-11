"""
CAPTCHA solving service plugin.

Speaks the createTask / getTaskResult JSON API that 2Captcha, Anti-Captcha,
CapSolver and CapMonster Cloud share. The host gives this plugin the chosen
service and account key in the challenge's meta, only for this call. What the
host passes in is already cleaned of personal details (core/captcha_privacy.py).
"""
import base64
import json
import os
import time

from openoptout_sdk import Plugin

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json"), encoding="utf-8") as _f:
    plugin = Plugin(json.load(_f))

# Task type names per service. None = that service doesn't solve this kind.
TASKS = {
    "recaptcha_v2": {"2captcha": "RecaptchaV2TaskProxyless", "anticaptcha": "RecaptchaV2TaskProxyless",
                     "capsolver": "ReCaptchaV2TaskProxyLess", "capmonster": "RecaptchaV2TaskProxyless"},
    "hcaptcha":     {"2captcha": "HCaptchaTaskProxyless", "anticaptcha": None,
                     "capsolver": None, "capmonster": None},
    "turnstile":    {"2captcha": "TurnstileTaskProxyless", "anticaptcha": "TurnstileTaskProxyless",
                     "capsolver": "AntiTurnstileTaskProxyLess", "capmonster": "TurnstileTask"},
    "image":        {"2captcha": "ImageToTextTask", "anticaptcha": "ImageToTextTask",
                     "capsolver": "ImageToTextTask", "capmonster": "ImageToTextTask"},
}
POLL_SECONDS = 5
MAX_WAIT = 120


def build_task(ch, service):
    kind = TASKS.get(ch.type, {}).get(service)
    if not kind:
        return None
    if ch.type == "image":
        if not ch.screenshot:
            return None
        return {"type": kind, "body": base64.b64encode(ch.screenshot).decode()}
    if not ch.site_key or not ch.page_url:
        return None
    return {"type": kind, "websiteURL": ch.page_url, "websiteKey": ch.site_key}


def answer_of(solution):
    for k in ("gRecaptchaResponse", "token", "text"):
        if solution.get(k):
            return k, solution[k]
    return None, None


def _post(base, path, payload):
    r = plugin.http.post(base + path, json.dumps(payload), {"Content-Type": "application/json"})
    if not r.get("ok"):
        raise RuntimeError(r.get("error") or "request failed")
    return json.loads(r.get("body") or "{}")


@plugin.solve_captcha
def solve(ch):
    meta = ch.meta or {}
    service, key, base = meta.get("service"), meta.get("api_key"), meta.get("service_base")
    if not (service and key and base):
        return {"defer_to_human": True}
    task = build_task(ch, service)
    if task is None:
        return {"defer_to_human": True}
    try:
        created = _post(base, "/createTask", {"clientKey": key, "task": task})
        if created.get("errorId"):
            return {"solved": False, "error": created.get("errorDescription") or created.get("errorCode") or "rejected"}
        task_id = created.get("taskId")
        waited = 0
        while waited < MAX_WAIT:
            time.sleep(POLL_SECONDS)
            waited += POLL_SECONDS
            res = _post(base, "/getTaskResult", {"clientKey": key, "taskId": task_id})
            if res.get("errorId"):
                return {"solved": False, "error": res.get("errorDescription") or "failed"}
            if res.get("status") == "ready":
                _, value = answer_of(res.get("solution") or {})
                if not value:
                    return {"solved": False, "error": "no answer in the reply"}
                # For a picture CAPTCHA the "token" is the text to type in.
                return {"solved": True, "token": value}
        return {"defer_to_human": True}
    except Exception as e:
        return {"solved": False, "error": str(e)[:200]}


if __name__ == "__main__":
    plugin.run()
