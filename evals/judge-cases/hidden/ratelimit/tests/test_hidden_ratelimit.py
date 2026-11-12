import threading
import time
import unittest

from ratelimit import TokenBucket


class HiddenTokenBucketTest(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.clock = lambda: self.now[0]

    def test_rule3_fractional_refill(self):
        bucket = TokenBucket(1, 0.5, self.clock)
        self.assertTrue(bucket.allow())
        self.now[0] += 1.0
        self.assertFalse(bucket.allow())  # only 0.5 token
        self.now[0] += 1.0
        self.assertTrue(bucket.allow())

    def test_rule3_never_above_capacity(self):
        bucket = TokenBucket(3, 10, self.clock)
        self.now[0] += 1000
        self.assertAlmostEqual(bucket.available(), 3.0)
        self.assertTrue(bucket.allow(3))
        self.assertFalse(bucket.allow())

    def test_rule2_denied_call_removes_nothing(self):
        bucket = TokenBucket(5, 0, self.clock)
        self.assertTrue(bucket.allow(3))
        self.assertFalse(bucket.allow(3))
        self.assertTrue(bucket.allow(2))

    def test_rule4_clock_goes_backwards(self):
        bucket = TokenBucket(2, 1, self.clock)
        self.assertTrue(bucket.allow(2))
        self.now[0] -= 50.0
        self.assertFalse(bucket.allow())  # elapsed is zero, not negative, not an error
        self.assertAlmostEqual(bucket.available(), 0.0)
        self.now[0] += 1.0  # one second after the lower value
        self.assertAlmostEqual(bucket.available(), 1.0)
        self.assertTrue(bucket.allow())

    def test_rule5_available_does_not_consume(self):
        bucket = TokenBucket(2, 0, self.clock)
        self.assertAlmostEqual(bucket.available(), 2.0)
        self.assertAlmostEqual(bucket.available(), 2.0)
        self.assertIsInstance(bucket.available(), float)

    def test_rule6_errors(self):
        for args in ((0, 1), (-1, 1), (1, -0.1)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    TokenBucket(args[0], args[1], self.clock)
        bucket = TokenBucket(2, 1, self.clock)
        for cost in (0, -1, 3):
            with self.subTest(cost=cost):
                with self.assertRaises(ValueError):
                    bucket.allow(cost)
        self.assertAlmostEqual(bucket.available(), 2.0)

    def test_rule7_thread_safety(self):
        def slow_clock():
            time.sleep(0.0002)  # widen the window between reading and writing the token count
            return 0.0

        bucket = TokenBucket(200, 0, slow_clock)
        granted = []

        def worker():
            count = 0
            for _ in range(100):
                if bucket.allow():
                    count += 1
            granted.append(count)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(granted), 200)
