# Monitoring, alerts and log forwarding

**Admin → Monitoring and alerts** (super admins only) connects OpenOptOut to the tools you already run.

**What can leave the server from here:** counts, states, timestamps, and the names of brokers, plugins and checks. Never a family member's name, email address, phone number, street address or date of birth.

## Health checks and metrics

| Address | For | Access |
|---|---|---|
| `/api/health` | Is it running? (liveness) | public |
| `/api/health/ready` | Is everything working? 200 when every check passes, 503 when one fails | public; lists checks only |
| `/api/metrics` | Prometheus text format | the metrics token (`Authorization: Bearer …`) or a super admin's sign-in |

**Checks:**
- the database answers;
- scheduled jobs are running;
- no opt-out run is stuck (running for over 6 hours) or ended with an error;
- connected inboxes were read in the last 2 hours;
- free disk space is over 1 GB or 10%;
- the last backup worked (when backups are on);
- log servers can be reached.

**Metrics** (all gauges or counters, no labels that name anyone):

| Metric | What it counts |
|---|---|
| `openoptout_up`, `openoptout_build_info{version}`, `openoptout_uptime_seconds` | the app itself |
| `openoptout_requests{status}` | opt-out requests by status |
| `openoptout_brokers{enabled}`, `openoptout_brokers_auto_disabled` | brokers |
| `openoptout_captchas_waiting` | CAPTCHAs waiting for a person |
| `openoptout_family_members` | people being protected |
| `openoptout_inboxes{status}`, `openoptout_plugins{status}` | inboxes and plugins by state |
| `openoptout_job_last_success_timestamp_seconds{job}` | when each scheduled job last finished |
| `openoptout_disk_free_bytes` | free disk space |
| `openoptout_log_forwarded_total`, `openoptout_log_dropped_total` | log forwarding |
| `openoptout_webhooks_total{result}` | webhook messages by result |

The metrics token is shown once when you make it. Only its hash is stored. Making a new one replaces the old one.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: openoptout
    scheme: https
    metrics_path: /api/metrics
    authorization: { credentials: oo_metrics_... }
    static_configs: [{ targets: ["optout.example.org"] }]
```

## Webhook notifications

| Service | Address to paste | Secret |
|---|---|---|
| ntfy | the topic, e.g. `https://ntfy.sh/your-topic` | access token, if the topic is protected |
| Gotify | `https://gotify.example.org/message` | app token |
| Slack | an incoming webhook address | (in the address) |
| Microsoft Teams | a Workflows webhook address ("Post to a channel when a webhook request is received") | (in the address) |
| Discord | a channel webhook address | (in the address) |
| Home Assistant | `http://homeassistant.local:8123/api/webhook/<id>` | (in the address) |
| Other (JSON) | any address that takes a JSON POST | optional signing secret: `X-OpenOptOut-Signature: sha256=<HMAC of the body>` |

Addresses and secrets are stored encrypted. For Slack, Teams, Discord and Home Assistant the address itself is the secret, so the page shows only its host.

**Events** (choose per webhook):
- opt-outs were sent;
- something waits for a person (at most every 4 hours);
- a broker was turned off after failing;
- listings came back after removal;
- a backup didn't work;
- a certificate needs attention;
- a plugin kept crashing and was turned off;
- a health check fails, and when every check passes again. Only the change is sent, not every five-minute check.

**What a message can hold is fixed in `core/webhooks.py`.** Each event has a short list of allowed details: counts, a broker or plugin name. Anything else is refused. Email addresses and phone numbers are blanked. Every message is also checked against every saved name, email, phone and address, the same check the AI helpers use. A message that matches is not sent, and the refusal is counted.

Messages go out on a background thread. A service that's down never slows OpenOptOut. The page shows each webhook's last result, and **Send a test** checks one straight away.

## Log forwarding

Copies of the System logs can go to a central log server:

| Kind | Sends to | Works with |
|---|---|---|
| Syslog | RFC 5424 over UDP, TCP or TLS (octet-counted framing on TCP/TLS) | rsyslog, syslog-ng, Graylog, most SIEMs |
| OpenTelemetry (OTLP) | `POST <address>/v1/logs`, JSON | OpenTelemetry Collector, Grafana Alloy, Loki 3, Graylog 6.1+, Splunk via its collector |
| Grafana Loki | `POST <address>/loki/api/v1/push` | Loki |
| Splunk HTTP Event Collector | `POST <address>/services/collector/event` with the HEC token | Splunk |

Choose which lines to send: everything, information and up, warnings and up, or errors only.

**Before a line leaves, it's scrubbed** the same way as the log file: tokens, passwords and secrets are removed. Email addresses and phone numbers are also replaced with `[email]` and `[number]`. Logs are meant to hold no personal details in the first place. This is a second net.

Lines wait in a queue of 10,000 and are sent in batches every two seconds. If the server can't keep up, the oldest lines are dropped and counted (shown on the page and in `openoptout_log_dropped_total`). OpenOptOut itself is never slowed down. The sender's own connection logs are never forwarded, so nothing loops.

## Not tested against live services yet

The message formats follow each service's documentation. Tests cover them with a fake sender. They haven't yet been sent to real ntfy, Gotify, Slack, Teams, Discord, Home Assistant, Graylog, Loki or Splunk instances. Use **Send a test** for each one you set up.
