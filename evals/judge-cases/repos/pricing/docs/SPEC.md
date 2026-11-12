# Money rules for the shop package

Amounts enter and leave the package as Python `float` or `int`. Callers and the JSON API depend on that.

1. `round_price(value)` returns a `float` with two decimals. A half cent rounds away from zero:
   2.675 gives 2.68 and -2.675 gives -2.68.
2. A number means what it shows when printed. 2.675 is two euros and 67.5 cents, although the binary
   float is a little smaller. The same applies to 1.005, which gives 1.01.
3. All arithmetic on money (price x quantity, amount x tax rate, sums) is exact decimal arithmetic on the
   numbers as written. Rounding is done one time, on the exact result. 1.005 x 3 is exactly 3.015,
   and gives 3.02.
4. `line_total(unit_price, qty)` is `unit_price x qty`, rounded as in rule 1.
5. `tax_for(amount, rate)` is `amount x rate`, rounded as in rule 1. A rate of 0.175 means 17.5%.
6. `invoice(lines, rate)` returns a dict with `subtotal` (the sum of the line totals), `tax`
   (`tax_for(subtotal, rate)`) and `total` (`subtotal + tax`). The three values are `float`, and the dict
   can be given to `json.dumps`.
