"""Token bucket rate limiter.

Rules
1. TokenBucket(capacity, refill_per_second, clock). `clock` is a function without arguments that returns
   the time in seconds as a float. The bucket starts full.
2. allow(cost=1) returns True and removes `cost` tokens when at least `cost` tokens are available.
   Otherwise it returns False and removes nothing.
3. Tokens refill continuously: elapsed seconds x refill_per_second. Fractions of a token count.
   The bucket never holds more than `capacity`.
4. If the clock returns a value lower than the last value seen, the elapsed time is zero, and the next
   refill is measured from that lower value.
5. available() returns the current number of tokens as a float, after the refill, and removes nothing.
6. ValueError: capacity <= 0, refill_per_second < 0, cost <= 0, or cost > capacity.
7. The class is thread-safe: concurrent calls to allow() never grant more tokens than the bucket holds.
"""


class TokenBucket:
    def __init__(self, capacity, refill_per_second, clock):
        raise NotImplementedError

    def allow(self, cost=1):
        raise NotImplementedError

    def available(self):
        raise NotImplementedError
