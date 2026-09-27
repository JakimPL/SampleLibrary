from __future__ import annotations

import math
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, IPv6Network
from typing import Final

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from samplecore.config import VisitorLimits
from sampleserver.addresses import parsed_address
from sampleserver.messages import MORPHS_BUSY, TOO_MANY_MORPHS, TOO_MANY_REQUESTS

# How many visitors' budgets are held at once; the one idle longest is forgotten first, which leaves
# a visitor so long idle a full budget, as waiting would have anyway.
MAXIMUM_TRACKED_VISITORS: Final[int] = 65_536
# An IPv6 host is handed a whole /64 network, so its addresses count as one visitor.
IPV6_VISITOR_PREFIX: Final[int] = 64
UNKNOWN_VISITOR: Final[str] = "unknown"
SECONDS_PER_MINUTE: Final[float] = 60.0
RETRY_AFTER_HEADER: Final[str] = "Retry-After"
# The answers built over the whole catalog, which cost a visitor `VisitorLimits.whole_catalog_weight`;
# the listings page through it, a page at a time as a person scrolls, and cost a request each.
WHOLE_CATALOG_PATHS: Final[frozenset[str]] = frozenset(
    {"/stats", "/cloud", "/cloud/categories", "/cloud/category-tags", "/cloud/modules"}
)
UNLIMITED_PATHS: Final[frozenset[str]] = frozenset({"/health"})

Clock = Callable[[], float]


def monotonic_seconds() -> float:
    """The clock a budget refills by: seconds on a clock no change of the wall clock moves."""
    return time.monotonic()


def visitor_of(connection: HTTPConnection, *, address_header: str) -> str:
    """The visitor a request comes from: the address the platform names in ``address_header``, else the peer.

    An IPv6 address counts by its /64 network, which one host holds whole, and an IPv4 address
    carried in IPv6 counts as itself.
    """
    named = connection.headers.get(address_header)
    peer = connection.client.host if connection.client is not None else None
    for candidate in (named, peer):
        address = parsed_address(candidate)
        if address is not None:
            return _visitor(address)
    return UNKNOWN_VISITOR


def _visitor(address: IPv4Address | IPv6Address) -> str:
    if isinstance(address, IPv6Address):
        return str(IPv6Network((address, IPV6_VISITOR_PREFIX), strict=False))
    return str(address)


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBudget:
    """A budget of ``capacity`` tokens refilled at ``refill_per_second``, spent by ``take``, one per key.

    A key's budget starts full. Up to `MAXIMUM_TRACKED_VISITORS` keys are held, the one idle longest
    forgotten first, so the table stays bounded whoever sends requests.
    """

    def __init__(self, *, capacity: float, refill_per_second: float, clock: Clock) -> None:
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def take(self, key: str, cost: float) -> float | None:
        """Spend ``cost`` tokens of ``key``'s budget; ``None`` once spent, or the seconds until the budget holds them."""
        bucket = self._refilled(key)
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return None
        return (cost - bucket.tokens) / self._refill_per_second

    def charge(self, key: str, cost: float) -> None:
        """Spend ``cost`` tokens of ``key``'s budget after the fact, into debt where the budget holds fewer."""
        self._refilled(key).tokens -= cost

    def _refilled(self, key: str) -> _Bucket:
        now = self._clock()
        bucket = self._buckets.pop(key, None) or _Bucket(tokens=self._capacity, updated_at=now)
        bucket.tokens = min(self._capacity, bucket.tokens + (now - bucket.updated_at) * self._refill_per_second)
        bucket.updated_at = now
        self._buckets[key] = bucket
        while len(self._buckets) > MAXIMUM_TRACKED_VISITORS:
            self._buckets.popitem(last=False)
        return bucket


class VisitorRequestLimits:
    """Middleware holding each visitor to the request budget of `VisitorLimits`, on the API's paths.

    A whole-catalog answer costs `VisitorLimits.whole_catalog_weight` requests, since it is what a
    flood would ask for; the health check costs nothing, since the platform asks it. A request past
    the budget is answered 429 with the seconds until the budget holds it again.
    """

    def __init__(
        self, app: ASGIApp, *, limits: VisitorLimits, api_prefix: str, clock: Clock = monotonic_seconds
    ) -> None:
        self._app = app
        self._limits = limits
        self._api_prefix = api_prefix
        self._budget = TokenBudget(capacity=limits.burst, refill_per_second=limits.refill_per_second, clock=clock)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        cost = self._cost(scope)
        if cost is not None:
            connection = HTTPConnection(scope)
            wait = self._budget.take(visitor_of(connection, address_header=self._limits.address_header), cost)
            if wait is not None:
                response = JSONResponse(
                    {"detail": TOO_MANY_REQUESTS},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={RETRY_AFTER_HEADER: str(math.ceil(wait))},
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)

    def _cost(self, scope: Scope) -> float | None:
        """What a request costs its visitor, or ``None`` for one the budget leaves alone."""
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith(f"{self._api_prefix}/"):
            return None
        route = path.removeprefix(self._api_prefix).rstrip("/")
        if route in UNLIMITED_PATHS:
            return None
        return float(self._limits.whole_catalog_weight if route in WHOLE_CATALOG_PATHS else 1)


class MorphGate:
    """What a morph asks of the renderer: one visitor's budget, everyone's, and a place among the renders in flight.

    A morph a browser already holds is answered 304 by the renderer at no cost, so a request naming
    the render it holds is charged only once the renderer answers with new audio; any other is
    charged before the renderer is asked. At most ``concurrent`` requests reach the renderer at once,
    which renders one at a time; one past them is turned away at once, since waiting would only hold
    a connection while the renderer works through the others.
    """

    def __init__(self, limits: VisitorLimits, *, clock: Clock = monotonic_seconds) -> None:
        refill = limits.morphs_per_minute / SECONDS_PER_MINUTE
        overall_refill = limits.morphs_per_minute_overall / SECONDS_PER_MINUTE
        self._address_header = limits.address_header
        self._visitors = TokenBudget(capacity=limits.morphs_per_minute, refill_per_second=refill, clock=clock)
        self._everyone = TokenBudget(
            capacity=limits.morphs_per_minute_overall, refill_per_second=overall_refill, clock=clock
        )
        self._concurrent = limits.concurrent_morphs
        self._in_flight = 0

    def visitor(self, connection: HTTPConnection) -> str:
        return visitor_of(connection, address_header=self._address_header)

    def admit(self, visitor: str) -> None:
        """Spend one morph of the visitor's budget and everyone's before the renderer is asked.

        Raises:
            HTTPException: 429 with the seconds to wait, once either budget is spent.
        """
        for key, budget in ((visitor, self._visitors), (UNKNOWN_VISITOR, self._everyone)):
            wait = budget.take(key, 1.0)
            if wait is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=TOO_MANY_MORPHS,
                    headers={RETRY_AFTER_HEADER: str(math.ceil(wait))},
                )

    def charge(self, visitor: str) -> None:
        """Spend one morph of both budgets after the renderer answered with new audio."""
        self._visitors.charge(visitor, 1.0)
        self._everyone.charge(UNKNOWN_VISITOR, 1.0)

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one of the places among the renders in flight for the length of the block.

        The morph route runs on the server's event loop, one step at a time, so the count of renders
        in flight changes between the steps of one request alone.

        Raises:
            HTTPException: 503 while every place is taken.
        """
        if self._in_flight >= self._concurrent:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MORPHS_BUSY)
        self._in_flight += 1
        try:
            yield
        finally:
            self._in_flight -= 1
