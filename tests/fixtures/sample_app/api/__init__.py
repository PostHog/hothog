"""The api package pulls every view at import time — like a router collecting endpoints.

billing and reports both import heavy_sdk at module scope (so it loads on boot) but only use
it inside functions (so it CAN be deferred). They funnel through THIS module, so the dominator
cut-point for heavy_sdk is `sample_app.api`.
"""

from sample_app.api import billing, reports, settings  # noqa: F401
