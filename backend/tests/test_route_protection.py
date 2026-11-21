"""Fails as soon as an endpoint is added without authentication or authorization."""

from app.authz.deps import get_authenticated, get_pending_two_factor
from app.main import create_app
from tests.routes import MIN_ROUTES, api_routes, dependency_calls

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    ("GET", "/api/v1/auth/invitations/{token}"),
    ("POST", "/api/v1/auth/invitations/{token}/accept"),
    # Calendar apps cannot sign in; the secret token in the URL is the credential.
    ("GET", "/api/v1/calendar-feeds/{token}.ics"),
}


def test_finds_all_routes() -> None:
    assert len(list(api_routes(create_app()))) >= MIN_ROUTES


def test_every_org_route_requires_a_permission() -> None:
    unprotected = [
        f"{method} {path}"
        for method, path, route in api_routes(create_app())
        if path.startswith("/api/v1/orgs/")
        and not any(
            hasattr(call, "__authz_permission__") for call in dependency_calls(route.dependant)
        )
    ]
    assert unprotected == []


def test_every_non_public_route_requires_a_session() -> None:
    unauthenticated = [
        f"{method} {path}"
        for method, path, route in api_routes(create_app())
        if (method, path) not in PUBLIC
        and not {get_authenticated, get_pending_two_factor} & set(dependency_calls(route.dependant))
    ]
    assert unauthenticated == []
