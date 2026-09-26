# Example plugins

The four email-provider reference plugins (`email-gmail`, `email-outlook`,
`email-yahoo`, `email-smtp`) that used to live only here now also live under
`backend/plugins/bundled/` — that's the copy that actually ships inside the
running app (Docker image / native install), so they can be auto-installed
when an operator picks that provider via OAuth in the setup wizard (see
`core/provider_plugins.py`). Keep both copies in sync if you change one, or
better: edit the one under `backend/plugins/bundled/` and copy it back here.

The other three (`example-broker-filler`, `example-request-watchdog`,
`example-tracker`) are purely illustrative and aren't bundled anywhere — they
exist to show the plugin API, not to be installed automatically.
