import unittest

from measure import balanced_orders


class MeasurementOrderTest(unittest.TestCase):
    def test_three_repeats_balance_every_api_position(self):
        orders = balanced_orders()
        self.assertEqual(3, len(orders))
        self.assertEqual(
            {"baseline", "direct_kotlin", "compatibility"},
            set(orders[0]),
        )
        for position in range(3):
            self.assertEqual(
                {"baseline", "direct_kotlin", "compatibility"},
                {order[position] for order in orders},
            )


if __name__ == "__main__":
    unittest.main()
