"""Fails as soon as an endpoint is added without authentication or authorization."""

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.authz.deps import get_authenticated
from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    ("GET", "/api/v1/auth/invitations/{token}"),
    ("POST", "/api/v1/auth/invitations/{token}/accept"),
}


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _calls(dep)


def _routes(app: FastAPI) -> Iterator[tuple[str, str, APIRoute]]:
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or ():
                yield method, route.path, route


def test_every_org_route_requires_a_permission() -> None:
    unprotected = [
        f"{method} {path}"
        for method, path, route in _routes(create_app())
        if path.startswith("/api/v1/orgs/")
        and not any(hasattr(call, "__authz_permission__") for call in _calls(route.dependant))
    ]
    assert unprotected == []


def test_every_non_public_route_requires_a_session() -> None:
    unauthenticated = [
        f"{method} {path}"
        for method, path, route in _routes(create_app())
        if (method, path) not in PUBLIC and get_authenticated not in set(_calls(route.dependant))
    ]
    assert unauthenticated == []
