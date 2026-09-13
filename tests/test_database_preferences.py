from __future__ import annotations

import os
import tempfile
import unittest

from database.database import Database


class DatabasePreferencesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.db = Database(self.path)
        await self.db.connect()
        await self.db.init_schema()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        os.unlink(self.path)

    async def test_clear_preferred_name_keeps_other_preferences(self) -> None:
        await self.db.upsert_user_preferences(
            1,
            2,
            preferred_name="Игровая",
            user_limit=10,
            bitrate=96000,
            privacy_mode="locked_hidden",
        )

        await self.db.clear_user_preferred_name(1, 2)
        preferences = await self.db.get_user_preferences(1, 2)

        self.assertIsNone(preferences.preferred_name)
        self.assertEqual(preferences.user_limit, 10)
        self.assertEqual(preferences.bitrate, 96000)
        self.assertEqual(preferences.privacy_mode, "locked_hidden")

    async def test_preference_permissions_do_not_store_room_name(self) -> None:
        await self.db.set_preference_permission(1, 2, 3, "allow")
        preferences = await self.db.get_user_preferences(1, 2)

        self.assertIsNone(preferences.preferred_name)


if __name__ == "__main__":
    unittest.main()
