"""Tax."""
from shop.pricing import round_price


def tax_for(amount, rate):
    return round_price(amount * rate)
