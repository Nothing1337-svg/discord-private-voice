from __future__ import annotations

import unittest

from utils.helpers import make_blocked_room_overwrite, make_privileged_room_overwrite, make_public_room_overwrite


class PermissionMatrixTest(unittest.TestCase):
    def test_public_room_states_are_independent(self) -> None:
        cases = {
            "open_visible": (False, False, True, True),
            "closed_visible": (True, False, True, False),
            "open_hidden": (False, True, False, True),
            "closed_hidden": (True, True, False, False),
        }

        for name, (locked, hidden, view_channel, connect) in cases.items():
            with self.subTest(name):
                overwrite = make_public_room_overwrite(locked=locked, hidden=hidden)

                self.assertIs(overwrite.view_channel, view_channel)
                self.assertIs(overwrite.connect, connect)
                self.assertIs(overwrite.speak, True)
                self.assertIs(overwrite.use_voice_activation, True)
                self.assertIs(overwrite.stream, True)

    def test_owner_and_allow_list_get_full_voice_access(self) -> None:
        overwrite = make_privileged_room_overwrite()

        self.assertIs(overwrite.view_channel, True)
        self.assertIs(overwrite.connect, True)
        self.assertIs(overwrite.speak, True)
        self.assertIs(overwrite.use_voice_activation, True)
        self.assertIs(overwrite.stream, True)

    def test_block_list_only_denies_connect(self) -> None:
        overwrite = make_blocked_room_overwrite()

        self.assertIsNone(overwrite.view_channel)
        self.assertIs(overwrite.connect, False)
        self.assertIsNone(overwrite.speak)
        self.assertIsNone(overwrite.use_voice_activation)
        self.assertIsNone(overwrite.stream)


if __name__ == "__main__":
    unittest.main()
