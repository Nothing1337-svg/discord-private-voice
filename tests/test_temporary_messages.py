from __future__ import annotations

import asyncio
import unittest

from utils.helpers import (
    ERROR_MESSAGE_DELETE_SECONDS,
    TEMP_MESSAGE_DELETE_SECONDS,
    delete_after_for,
    safe_delete_message_later,
)


class FakeMessage:
    id = 123

    def __init__(self) -> None:
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class TemporaryMessagesTest(unittest.IsolatedAsyncioTestCase):
    def test_delete_after_policy(self) -> None:
        self.assertEqual(delete_after_for(ephemeral=False), TEMP_MESSAGE_DELETE_SECONDS)
        self.assertEqual(delete_after_for(ephemeral=False, is_error=True), ERROR_MESSAGE_DELETE_SECONDS)
        self.assertIsNone(delete_after_for(ephemeral=True))
        self.assertIsNone(delete_after_for(ephemeral=True, is_error=True))

    async def test_safe_delete_message_later_runs_in_background(self) -> None:
        message = FakeMessage()

        safe_delete_message_later(message, 0.01)

        self.assertFalse(message.deleted)
        await asyncio.sleep(0.03)
        self.assertTrue(message.deleted)


if __name__ == "__main__":
    unittest.main()
