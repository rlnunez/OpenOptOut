"""
PrivacyShield Plugin SDK (Backwards Compatibility Alias)
========================================================

Re-exports the complete OpenOptOut Plugin SDK for backwards compatibility
with legacy plugins importing privacyshield_sdk.
"""

try:
    from .openoptout_sdk import *
    from .openoptout_sdk import (
        Plugin, manifest, FormResult, CaptchaChallenge, EmailMessage,
        FormContext, Event, PermissionDenied, _PluginServicer, _HostClient
    )
except (ImportError, ValueError):
    from openoptout_sdk import *
    from openoptout_sdk import (
        Plugin, manifest, FormResult, CaptchaChallenge, EmailMessage,
        FormContext, Event, PermissionDenied, _PluginServicer, _HostClient
    )
