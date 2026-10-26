from agent_authz_bench.gateway.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_sliding_window_limit() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock=clock)
    assert limiter.check("k", calls=2, period_seconds=10).allowed
    assert limiter.check("k", calls=2, period_seconds=10).allowed
    denied = limiter.check("k", calls=2, period_seconds=10)
    assert not denied.allowed
    assert denied.retry_after is not None
    clock.advance(11)
    assert limiter.check("k", calls=2, period_seconds=10).allowed
