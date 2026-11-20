import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from chat import ChatReader, CombatRow, LogLine, parse_log_line


class TestChatParsing(unittest.TestCase):

    def _internal(self, line, expected):
        log_line = parse_log_line(line)
        self.assertEqual(log_line, expected)

    def test_parse_system_message(self):
        msg = "2021-09-21 09:42:35 [System] [] Critical hit - Additional damage! You inflicted 519.1 points of damage"
        expected = LogLine(
            "2021-09-21 09:42:35",
            "System",
            "",
            "Critical hit - Additional damage! You inflicted 519.1 points of damage"
        )
        self._internal(msg, expected)

    def test_parse_global_message(self):
        msg = "2021-09-21 09:46:31 [Globals] [] Nanashana Nana Itsanai killed a creature " \
              "(Desert Crawler Provider) with a value of 416 PED!"
        expected = LogLine(
            "2021-09-21 09:46:31",
            "Globals",
            "",
            "Nanashana Nana Itsanai killed a creature (Desert Crawler Provider) with a value of 416 PED!"
        )
        self._internal(msg, expected)

    def test_parse_global_message_brood(self):
        msg = "2021-09-21 09:46:31 [Globals] [] Nanashana Nana Itsanai killed a creature " \
              "(Disecter, Brood of Bram) with a value of 91 PED!"
        expected = LogLine(
            "2021-09-21 09:46:31",
            "Globals",
            "",
            "Nanashana Nana Itsanai killed a creature (Disecter, Brood of Bram) with a value of 91 PED!"
        )
        self._internal(msg, expected)

    def test_parse_global_message_with_apostrophe_name(self):
        msg = "2021-09-21 09:46:31 [Globals] [] Na'na'sha'na Na'na It'san'ai killed a creature " \
              "(Desert Crawler Provider) with a value of 416 PED!"
        expected = LogLine(
            "2021-09-21 09:46:31",
            "Globals",
            "",
            "Na'na'sha'na Na'na It'san'ai killed a creature (Desert Crawler Provider) with a value of 416 PED!"
        )
        self._internal(msg, expected)


class TestChatReader(unittest.TestCase):

    def _make_reader(self, path):
        app = SimpleNamespace(
            config=SimpleNamespace(
                location=SimpleNamespace(value=path)
            )
        )
        return ChatReader(app)

    def _wait_for_line(self, reader):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            line = reader.getline()
            if line is not None:
                return line
            time.sleep(0.01)
        self.fail("Timed out waiting for a parsed chat line")

    def test_getlines_preserves_rows_after_batch_limit(self):
        reader = self._make_reader("")
        rows = [object() for _ in range(8)]
        for row in rows:
            reader.lines.put_nowait(row)

        self.assertEqual(reader.getlines(6), rows[:6])
        self.assertEqual(reader.getlines(100), rows[6:])

    def test_stop_reader_can_preserve_queued_rows_for_shutdown(self):
        reader = self._make_reader("")
        row = object()
        reader.lines.put_nowait(row)

        self.assertTrue(reader.stop_reader(clear_pending=False))
        self.assertEqual(reader.getlines(1), [row])

    def test_full_queue_backpressures_without_dropping_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "chat.log")
            with open(path, "w", encoding="utf-8") as chat_log:
                for damage in ("10.0", "20.0"):
                    chat_log.write(
                        "2021-09-21 09:42:35 [System] [] "
                        f"You inflicted {damage} points of damage\n"
                    )

            with patch("chat.MAX_QUEUED_CHAT_ROWS", 1):
                reader = self._make_reader(path)
                reader.delay_start_reader()
                try:
                    deadline = time.monotonic() + 2
                    while reader.lines.qsize() == 0 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(reader.lines.maxsize, 1)
                    first = reader.getline()
                    self.assertIsNotNone(first)
                    self.assertEqual(first.amount, 10.0)
                    self.assertEqual(self._wait_for_line(reader).amount, 20.0)
                finally:
                    reader.stop_reader()

    def test_reader_continues_after_malformed_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "chat.log")
            with open(path, "w", encoding="utf-8") as chat_log:
                chat_log.write(
                    "2021-99-99 99:99:99 [System] [] "
                    "You inflicted 123.4 points of damage\n"
                )
                chat_log.write(
                    "2021-09-21 09:42:35 [System] [] "
                    "You inflicted 519.1 points of damage\n"
                )

            reader = self._make_reader(path)
            try:
                reader.delay_start_reader()
                line = self._wait_for_line(reader)
                self.assertIsInstance(line, CombatRow)
                self.assertEqual(line.amount, 519.1)
                self.assertTrue(reader.reader.is_alive())
            finally:
                reader.stop_reader()

    def test_reader_restarts_for_new_path_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = os.path.join(directory, "first.log")
            second_path = os.path.join(directory, "second.log")
            for path, damage in ((first_path, "10.0"), (second_path, "20.0")):
                with open(path, "w", encoding="utf-8") as chat_log:
                    chat_log.write(
                        "2021-09-21 09:42:35 [System] [] "
                        f"You inflicted {damage} points of damage\n"
                    )

            reader = self._make_reader(first_path)
            try:
                reader.delay_start_reader()
                self.assertEqual(self._wait_for_line(reader).amount, 10.0)
                reader.app.config.location.value = second_path
                reader.delay_start_reader()
                self.assertEqual(self._wait_for_line(reader).amount, 20.0)
                thread = reader.reader
                self.assertTrue(reader.stop_reader())
                self.assertFalse(thread.is_alive())
            finally:
                reader.stop_reader()

    def test_reader_retries_after_missing_file_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "chat.log")
            reader = self._make_reader(path)
            with patch("chat.READER_RETRY_DELAY", 0):
                reader.delay_start_reader()
                deadline = time.monotonic() + 2
                while reader.last_error is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertIsNotNone(reader.last_error)

                with open(path, "w", encoding="utf-8") as chat_log:
                    chat_log.write(
                        "2021-09-21 09:42:35 [System] [] "
                        "You inflicted 30.0 points of damage\n"
                    )
                reader.delay_start_reader()
                self.assertEqual(self._wait_for_line(reader).amount, 30.0)
                self.assertIsNone(reader.last_error)
                reader.stop_reader()


if __name__ == '__main__':
    unittest.main()
