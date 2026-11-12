import unittest

from ratelimit import TokenBucket


class TokenBucketTest(unittest.TestCase):
    def test_starts_full_and_refills(self):
        now = [0.0]
        bucket = TokenBucket(2, 1, lambda: now[0])
        self.assertTrue(bucket.allow())
        self.assertTrue(bucket.allow())
        self.assertFalse(bucket.allow())
        now[0] = 1.0
        self.assertTrue(bucket.allow())


if __name__ == "__main__":
    unittest.main()
