import unittest

from publisher import merge, publish


class PublicationTests(unittest.TestCase):
    def exercise(self, operation, change=None, initial_time=1, expected=True):
        clock = [initial_time]
        owner = dict(scope="PUBLISHER", owner_id="a", token="t",
                     acquired_at=0, expires_at=5)
        output = ["prior"]
        prepared_calls = []
        expected_owner = owner.copy()

        def prepare(value):
            prepared_calls.append(value)
            if change:
                change(owner, clock)
            expected_owner.clear()
            expected_owner.update(owner)
            return value.upper()

        self.assertIs(operation("value", owner, prepare, lambda: clock[0], output), expected)
        self.assertEqual(owner, expected_owner)
        appended = {"merged": "VALUE"} if operation is merge else "VALUE"
        self.assertEqual(output, ["prior", appended] if expected else ["prior"])
        self.assertEqual(prepared_calls, [] if initial_time >= 5 else ["value"])

    def test_valid_outputs(self):
        for operation in (publish, merge):
            with self.subTest(operation=operation.__name__):
                self.exercise(operation)

    def test_expired_at_entry_does_not_prepare(self):
        for operation in (publish, merge):
            with self.subTest(operation=operation.__name__):
                self.exercise(operation, initial_time=5, expected=False)

    def test_prepare_crosses_expiry_including_exact_boundary(self):
        for operation in (publish, merge):
            for completion_time in (5, 6):
                with self.subTest(operation=operation.__name__, time=completion_time):
                    self.exercise(operation, lambda owner, clock: clock.__setitem__(0, completion_time), expected=False)

    def test_prepare_finishes_before_expiry(self):
        for operation in (publish, merge):
            with self.subTest(operation=operation.__name__):
                self.exercise(operation, lambda owner, clock: clock.__setitem__(0, 4))

    def test_each_identity_field_changes(self):
        for operation in (publish, merge):
            for field, replacement in (("owner_id", "b"), ("token", "other"), ("acquired_at", 2)):
                with self.subTest(operation=operation.__name__, field=field):
                    self.exercise(operation, lambda owner, clock: owner.__setitem__(field, replacement), expected=False)

    def test_scope_changes(self):
        for operation in (publish, merge):
            with self.subTest(operation=operation.__name__):
                self.exercise(operation, lambda owner, clock: owner.__setitem__("scope", "OTHER"), expected=False)

    def test_expiry_changes(self):
        for operation in (publish, merge):
            with self.subTest(operation=operation.__name__):
                self.exercise(operation, lambda owner, clock: owner.__setitem__("expires_at", 1), expected=False)


if __name__ == "__main__":
    unittest.main()
