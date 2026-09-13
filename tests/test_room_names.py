from __future__ import annotations

import unittest

from utils.helpers import room_name_for


class FakeMember:
    display_name = "Fedor"


class RoomNamesTest(unittest.TestCase):
    def test_new_room_name_is_always_default(self) -> None:
        member = FakeMember()

        self.assertEqual(room_name_for(member), "Комната • Fedor")
        self.assertEqual(room_name_for(member), "Комната • Fedor")


if __name__ == "__main__":
    unittest.main()
