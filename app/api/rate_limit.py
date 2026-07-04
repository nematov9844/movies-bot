"""Shared slowapi ``Limiter`` (Phase 15).

Lives in its own module rather than ``api_main.py`` so route modules
(``auth.py``, for the login-specific override) can import it without a
circular import — ``api_main.py`` is the one that imports every route
module to register its router.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Per the TZ: 60/min for everything, 5/min specifically for login (applied
# as a per-route override via @limiter.limit in auth.py).
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
