# Example plugins

Organized the same way installed plugins are, one folder per plugin type (`<type>/<id>/`), and every manifest declares its `type`:

```
email/     email-gmail, email-outlook, email-yahoo, email-smtp
forms/     example-broker-filler
general/   example-request-watchdog, example-tracker
```

The four email-provider plugins also live under `backend/plugins/bundled/email/` — that's the copy that actually ships inside the running app (Docker image / native install). When an operator picks one of those providers via OAuth in the setup wizard, it's copied into `<plugins directory>/email/<id>/` and installed from there (see `core/provider_plugins.py` and `plugins/layout.py`). Keep both copies in sync if you change one, or better: edit the one under `backend/plugins/bundled/email/` and copy it back here.

The other three (`example-broker-filler`, `example-request-watchdog`, `example-tracker`) are purely illustrative and aren't bundled anywhere — they exist to show the plugin API, not to be installed automatically.
