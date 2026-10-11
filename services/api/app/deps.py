"""Dependency injection (task 5.1). Bootstrap: auth scheme only.

Concrete providers (WS2/WS3/WS4 packages, with fixture fallbacks) are wired here in task 5.1.
"""

from fastapi.security import HTTPBearer

# Declares the JWT bearer scheme in the OpenAPI contract. Token validation and
# ``require_roles`` arrive with task 5.3.
bearer = HTTPBearer(auto_error=False, description="JWT from POST /api/v1/auth/login")
