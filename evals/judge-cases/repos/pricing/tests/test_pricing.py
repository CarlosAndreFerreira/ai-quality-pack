import unittest

from shop.invoice import invoice
from shop.pricing import round_price


class PricingTest(unittest.TestCase):
    def test_half_cent_rounds_up(self):
        self.assertEqual(round_price(2.675), 2.68)

    def test_plain_values(self):
        self.assertEqual(round_price(1.0), 1.0)
        self.assertEqual(round_price(19.994), 19.99)

    def test_invoice(self):
        self.assertEqual(invoice([(10.0, 2)], 0.1), {"subtotal": 20.0, "tax": 2.0, "total": 22.0})


if __name__ == "__main__":
    unittest.main()
