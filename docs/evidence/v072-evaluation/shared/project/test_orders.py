import unittest

import orders


class IntSubclass(int):
    pass


class QuantityContractTests(unittest.TestCase):
    def test_all_entry_points_reject_non_builtin_or_out_of_range_values(self):
        invalid = (True, False, IntSubclass(1), IntSubclass(20), 0, -1, 21,
                   1.0, 20.0, "1", None, [], {})
        for name in ("check_quantity", "create_order", "amend_order",
                     "retry_order", "quote_order"):
            for quantity in invalid:
                with self.subTest(entry=name, quantity=repr(quantity),
                                  quantity_type=type(quantity).__name__):
                    with self.assertRaises(ValueError) as caught:
                        getattr(orders, name)(quantity)
                    self.assertEqual(str(caught.exception), "quantity")

    def test_every_valid_quantity_preserves_outputs(self):
        for quantity in range(1, 21):
            with self.subTest(quantity=quantity):
                self.assertEqual(orders.check_quantity(quantity), quantity)
                self.assertEqual(orders.quote_order(quantity), quantity * 3)
                for action in ("create", "amend", "retry"):
                    result = getattr(orders, action + "_order")(quantity)
                    self.assertEqual(result, {"quantity": quantity, "action": action})
                    self.assertIs(type(result["quantity"]), int)


if __name__ == "__main__":
    unittest.main()
