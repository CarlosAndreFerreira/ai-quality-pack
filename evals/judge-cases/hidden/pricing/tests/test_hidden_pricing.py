import json
import unittest

from shop.invoice import invoice, line_total
from shop.pricing import round_price
from shop.tax import tax_for


class HiddenPricingTest(unittest.TestCase):
    def test_rule1_half_away_from_zero(self):
        self.assertEqual(round_price(2.675), 2.68)
        self.assertEqual(round_price(-2.675), -2.68)
        self.assertEqual(round_price(2.674), 2.67)
        self.assertEqual(round_price(0.125), 0.13)
        self.assertEqual(round_price(0.135), 0.14)

    def test_rule1_returns_float(self):
        for value in (2.675, 3, 0, 10.0):
            self.assertIs(type(round_price(value)), float)
        self.assertEqual(round_price(3), 3.0)

    def test_rule2_number_as_written(self):
        self.assertEqual(round_price(1.005), 1.01)
        self.assertEqual(round_price(1.115), 1.12)

    def test_rule3_and_4_line_total_is_exact(self):
        self.assertEqual(line_total(1.005, 3), 3.02)   # float product is 3.0149999999999997
        self.assertEqual(line_total(1.025, 7), 7.18)   # float product is 7.175 minus a little
        self.assertEqual(line_total(19.99, 3), 59.97)
        self.assertIs(type(line_total(2, 3)), float)

    def test_rule5_tax_is_exact(self):
        self.assertEqual(tax_for(1.15, 0.1), 0.12)     # float product rounds to 0.11
        self.assertEqual(tax_for(3.0, 0.175), 0.53)    # float product rounds to 0.52
        self.assertEqual(tax_for(100, 0.23), 23.0)
        self.assertIs(type(tax_for(100, 0.23)), float)

    def test_rule6_invoice(self):
        result = invoice([(1.005, 3), (1.025, 7)], 0.175)
        # line totals 3.02 + 7.18 = 10.20; tax 10.20 x 0.175 = 1.785 -> 1.79; total 11.99
        self.assertEqual(result, {"subtotal": 10.2, "tax": 1.79, "total": 11.99})
        for key in ("subtotal", "tax", "total"):
            self.assertIs(type(result[key]), float)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_rule6_sum_has_no_float_noise(self):
        result = invoice([(0.1, 1), (0.2, 1), (0.3, 1)], 0)
        self.assertEqual(result, {"subtotal": 0.6, "tax": 0.0, "total": 0.6})
        self.assertEqual(invoice([], 0.23), {"subtotal": 0.0, "tax": 0.0, "total": 0.0})
