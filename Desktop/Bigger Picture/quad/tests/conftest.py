import pytest
from app.middleware.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset in-memory rate limit counters before each test so tests don't bleed into each other."""
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield
