"""The spend-control reports (`/api/v1/spend-controls/`, #465).

Two reads every workspace may make, whichever products it holds: Stops and
breaches (what was spent past a stop, and why) and Utilisation and headroom
(how much of each ceiling was used, and how often it could not be
evaluated). A handle of its own on the facade rather than a method on a
product client, because the reports read across the kernel's controls and
billing's — the same footing the routes have, at a prefix of their own and
gated on no product. Each method names an operation, never a route
(`docs/conventions/sdk-wrap.md`), and parses through the generated model.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ubb import _operations as ops
from ubb.exceptions import UBBConnectionError
from ubb._http import raise_for_status
from ubb._models import from_wire
from ubb.retry import request_with_retry
# Generated DTOs (the wrap, #84).
from ubb._core.models.stops_and_breaches_response import StopsAndBreachesResponse
from ubb._core.models.utilisation_and_headroom_response import (
    UtilisationAndHeadroomResponse)


def _filters(**given) -> dict:
    """The query parameters a report takes, with the absent ones left off
    (the route reads an omitted filter as no filter) and an instant sent as
    the ISO-8601 the route parses."""
    params = {}
    for name, value in given.items():
        if value is None:
            continue
        params[name] = value.isoformat() if isinstance(value, datetime) else value
    return params


class SpendControlsClient:
    """Client for the spend-control reports (/api/v1/spend-controls/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> SpendControlsClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internal request helper (same pattern as the product clients) ----

    def _request_once(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        raise_for_status(response)
        return response

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )

    # ---- the two reports ----

    def stops_and_breaches(self, *, customer_id: str | None = None,
                           task_type: str | None = None,
                           since: datetime | None = None,
                           until: datetime | None = None,
                           control_family: str | None = None
                           ) -> StopsAndBreachesResponse:
        """What was spent past a stop, and why — every spend control that
        fired and had an enforcement consequence in the window, as typed
        rows discriminated by `control_family`, via
        GET /api/v1/spend-controls/stops-and-breaches.

        Every argument is a filter and every filter is optional: a customer
        (its work and its billing owner's customer-wide episodes), a kind of
        work, a window on the instant each episode opened (the route bounds
        an open window to the 366 days ending now and echoes what it
        applied), and a family — pass a `ubb.vocabulary.CONTROL_FAMILY_*`
        constant; the route, not this client, refuses a word outside the
        set. A family the workspace lacks answers no rows, never an error.
        """
        r = self._request(*ops.API_V1_SPEND_CONTROL_ENDPOINTS_STOPS_AND_BREACHES,
                          params=_filters(customer_id=customer_id, task_type=task_type,
                                          since=since, until=until,
                                          control_family=control_family))
        return from_wire(StopsAndBreachesResponse, r.json())

    def utilisation_and_headroom(self, *, customer_id: str | None = None,
                                 task_type: str | None = None,
                                 since: datetime | None = None,
                                 until: datetime | None = None
                                 ) -> UtilisationAndHeadroomResponse:
        """How much of each ceiling was used, and how often it could not be
        evaluated — one row per unit of work that completed in the window
        with its ceiling status, utilisation and headroom at completion, and
        the aggregate computed per unit and then across every unit, via
        GET /api/v1/spend-controls/utilisation-and-headroom.

        The filters and the window are `stops_and_breaches`'s, on the
        instant each unit completed. Every average is `None` where no unit
        contributes — read it as unknown, never as zero. With a customer
        named, `customer_spend_pool` carries that customer's pool status
        pair where a pool applies.
        """
        r = self._request(*ops.API_V1_SPEND_CONTROL_ENDPOINTS_UTILISATION_AND_HEADROOM,
                          params=_filters(customer_id=customer_id, task_type=task_type,
                                          since=since, until=until))
        return from_wire(UtilisationAndHeadroomResponse, r.json())

    def close(self) -> None:
        self._http.close()
