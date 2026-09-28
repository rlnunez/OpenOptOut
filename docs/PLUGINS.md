# PrivacyShield Plugin System — Documentation

The plugin documentation is maintained as two guides that are **also rendered live inside the app** (Help → Using Plugins / Writing Plugins, super-admin only). Because the in-app pages read these files directly, they are the single source of truth and live next to the plugin code:

- **Administrator guide** — security model, permissions, safety controls, and how to install/enable/operate plugins: [`backend/plugins/docs/USING_PLUGINS.md`](../backend/plugins/docs/USING_PLUGINS.md)

- **Developer guide** — extension points, host capabilities, manifest format, and the SDK for writing plugins: [`backend/plugins/docs/WRITING_PLUGINS.md`](../backend/plugins/docs/WRITING_PLUGINS.md)

Edit those two files to update the documentation; the in-app Help pages will reflect the changes automatically (they read the files at request time).
