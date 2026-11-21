"""Every API route of the app, flattened across included routers."""

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

# Guards against a silently empty route list (FastAPI 0.16x nests included routers).
MIN_ROUTES = 150


def dependency_calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from dependency_calls(dep)


def api_routes(app: FastAPI) -> Iterator[tuple[str, str, Any]]:
    """(method, path, route) for every API route; route has `dependant` and `endpoint`."""
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute):
            for method in sorted(context.methods or ()):
                yield method, context.path or "", context
