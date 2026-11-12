"""Invoices."""
from shop.pricing import round_price
from shop.tax import tax_for


def line_total(unit_price, qty):
    return round_price(unit_price * qty)


def invoice(lines, rate):
    """lines: list of (unit_price, qty)."""
    subtotal = round_price(sum(line_total(price, qty) for price, qty in lines))
    tax = tax_for(subtotal, rate)
    return {"subtotal": subtotal, "tax": tax, "total": round_price(subtotal + tax)}
