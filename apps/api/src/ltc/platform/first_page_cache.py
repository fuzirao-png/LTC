"""Short-lived cache for authenticated first-page responses."""

import json
from collections.abc import Callable
from hashlib import sha256
from typing import TypeVar

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

_T = TypeVar("_T")


class FirstPageCache:
    def __init__(self, url: str) -> None:
        self._redis = Redis.from_url(
            url, socket_connect_timeout=0.15, socket_timeout=0.15, retry=Retry(NoBackoff(), 0),
        ) if url else None

    def get_or_load(self, parts: tuple[object, ...], load: Callable[[], _T], *, refresh: bool = False) -> _T:
        if self._redis is None:
            return load()
        digest = sha256(json.dumps(parts, default=str).encode()).hexdigest()
        key = f"ltc:first-page:v1:{digest}"
        if not refresh:
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    return json.loads(raw)
            except (RedisError, ValueError):
                pass
        value = load()
        try:
            # A miss that began before a refresh cannot overwrite the refreshed page.
            self._redis.set(key, json.dumps(jsonable_encoder(value)), ex=30, nx=not refresh)
        except RedisError:
            pass
        return value

    def close(self) -> None:
        if self._redis is not None:
            self._redis.close()


def first_page(request: Request, key: tuple[object, ...] | None, load: Callable[[], _T]) -> _T:
    cache = getattr(request.app.state, "first_page_cache", None)
    if key is None or cache is None:
        return load()
    directives = {value.strip().lower() for value in request.headers.get("cache-control", "").split(",")}
    return cache.get_or_load(key, load, refresh="no-cache" in directives)
