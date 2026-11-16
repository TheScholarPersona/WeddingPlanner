"""Load test: p95 response time of the main read endpoints under concurrent use.

Usage (against the running stack, with a demo organization):
    python scripts/loadtest.py --base https://localhost --email ... --password ... \
        [--users 20] [--seconds 30] [--budget-ms 300]

Each simulated user signs in once and then repeatedly opens the pages a planner uses most.
Exits with status 1 if any endpoint's p95 is above the budget.
"""

import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict
from datetime import date, timedelta

import httpx


async def session(base: str, email: str, password: str) -> tuple[httpx.AsyncClient, str, list[str]]:
    client = httpx.AsyncClient(base_url=base, verify=False, timeout=30)  # noqa: S501 - local CA
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    org = r.json()["memberships"][0]["organization_id"]
    weddings = (await client.get(f"/api/v1/orgs/{org}/projects")).json()
    return client, org, [w["id"] for w in weddings]


def endpoints(org: str, weddings: list[str]) -> list[tuple[str, str]]:
    today = date.today()
    start, end = today.replace(day=1), today.replace(day=1) + timedelta(days=41)
    w = random.choice(weddings)  # noqa: S311 - not security relevant
    p = f"/api/v1/orgs/{org}/projects/{w}"
    return [
        ("dashboard", f"/api/v1/orgs/{org}/dashboard"),
        ("weddings", f"/api/v1/orgs/{org}/projects"),
        ("wedding", p),
        ("tasks", f"{p}/tasks"),
        ("my tasks", f"/api/v1/orgs/{org}/tasks?status=open"),
        ("budget", f"{p}/budget"),
        ("documents", f"{p}/documents"),
        ("calendar", f"/api/v1/orgs/{org}/calendar?start={start}&end={end}"),
        ("activity", f"{p}/activity"),
    ]


async def user(
    base: str,
    cookies: httpx.Cookies,
    org: str,
    weddings: list[str],
    until: float,
    timings: dict[str, list[float]],
) -> int:
    # One sign-in shared by all simulated users (sign-ins are rate limited per account).
    client = httpx.AsyncClient(base_url=base, verify=False, timeout=30, cookies=cookies)  # noqa: S501
    errors = 0
    async with client:
        while time.monotonic() < until:
            for name, path in endpoints(org, weddings):
                t0 = time.perf_counter()
                r = await client.get(path)
                timings[name].append((time.perf_counter() - t0) * 1000)
                if r.status_code >= 400:
                    errors += 1
    return errors


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://localhost")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--budget-ms", type=float, default=300)
    args = parser.parse_args()

    timings: dict[str, list[float]] = defaultdict(list)
    until = time.monotonic() + args.seconds
    login, org, weddings = await session(args.base, args.email, args.password)
    errors = sum(
        await asyncio.gather(
            *(
                user(args.base, login.cookies, org, weddings, until, timings)
                for _ in range(args.users)
            )
        )
    )
    await login.aclose()
    total = sum(len(v) for v in timings.values())
    print(f"{args.users} users, {args.seconds} s, {total} requests, {errors} errors")
    print(f"{'endpoint':<12} {'n':>6} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}")
    worst = 0.0
    for name, values in timings.items():
        values.sort()
        p95 = values[int(len(values) * 0.95) - 1]
        worst = max(worst, p95)
        print(
            f"{name:<12} {len(values):>6} {statistics.median(values):>8.0f} {p95:>8.0f} "
            f"{values[-1]:>8.0f}"
        )
    ok = worst <= args.budget_ms and errors == 0
    verdict = "met" if ok else "NOT met"
    print(f"p95 budget {args.budget_ms:.0f} ms: {verdict} (worst p95 {worst:.0f} ms)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
