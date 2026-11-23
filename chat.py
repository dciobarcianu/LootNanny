import enum
import logging
import os
import queue
from datetime import datetime
from collections import namedtuple
import re
import time
import threading

from decimal import Decimal, InvalidOperation


logger = logging.getLogger(__name__)
MAX_QUEUED_CHAT_ROWS = 10000
CHAT_POLL_INTERVAL = 0.05
READER_RETRY_DELAY = 2


class ChatType(str, enum.Enum):
    HEAL = "heal"
    COMBAT = "combat"
    SKILL = "skill"
    DEATH = "death"
    EVADE = "evade"
    DAMAGE = "damage"
    DEFLECT = "deflect"
    DODGE = "dodge"
    ENHANCER = "enhancer"
    LOOT = "loot"
    GLOBAL = "global"


class BaseChatRow(object):

    def __init__(self, *args, **kwargs):
        self.time = None


class HealRow(BaseChatRow):

    def __init__(self, amount):
        super().__init__()
        self.amount = float(amount)


class CombatRow(BaseChatRow):

    def __init__(self, amount=0.0, critical=False, miss=False):
        super().__init__()
        self.amount = float(amount) if amount else 0.0
        self.critical = critical
        self.miss = miss


class SkillRow(BaseChatRow):

    def __init__(self, amount, skill):
        super().__init__()
        try:
            self.amount = float(amount)
            self.skill = skill
        except ValueError:
            # Attributes have their values swapped around in the chat message
            self.amount = float(skill)
            self.skill = amount


class EnhancerBreakages(BaseChatRow):

    def __init__(self, type):
        super().__init__()
        self.type = type


class LootInstance(BaseChatRow):
    CUSTOM_VALUES = {
        "Shrapnel": Decimal("0.0001")
    }

    def __init__(self, name, amount, value):
        super().__init__()
        self.name = name
        self.amount = int(amount)

        if name in self.CUSTOM_VALUES:
            self.value = Decimal(amount) * self.CUSTOM_VALUES[name]
        else:
            self.value = Decimal(value)


class GlobalInstance(BaseChatRow):

    def __init__(self, name, creature, value, location=None, hof=False):
        super().__init__()
        self.name = name
        self.creature = creature
        self.value = value
        self.hof = hof
        self.location = location

LOG_LINE_REGEX = re.compile(
    r"([\d\-]+ [\d:]+) \[(\w+)\] \[(.*)\] (.*)"
)

LogLine = namedtuple("LogLine", ["time", "channel", "speaker", "msg"])


def parse_log_line(line: str) -> LogLine:
    """
    Parses a raw string log line and returns an exploded LogLine for easier manipulation
    :param line: The line to process
    :return: LogLine
    """
    matched = LOG_LINE_REGEX.match(line)
    if not matched:
        return LogLine("", "", "", "")
    return LogLine(*matched.groups())


REGEXES = {
    re.compile(r"Critical hit - Additional damage! You inflicted (\d+\.\d+) points of damage"): (ChatType.DAMAGE, CombatRow, {"critical": True}),
    re.compile(r"You inflicted (\d+\.\d+) points of damage"): (ChatType.DAMAGE, CombatRow, {}),
    re.compile(r"You healed yourself (\d+\.\d+) points"): (ChatType.HEAL, HealRow, {}),
    re.compile(r"Damage deflected!"): (ChatType.DEFLECT, BaseChatRow, {}),
    re.compile(r"You Evaded the attack"): (ChatType.EVADE, BaseChatRow, {}),
    re.compile(r"You missed"): (ChatType.DODGE, CombatRow, {"miss": True}),
    re.compile(r"The target Dodged your attack"): (ChatType.DODGE, CombatRow, {"miss": True}),
    re.compile(r"The target Evaded your attack"): (ChatType.DODGE, CombatRow, {"miss": True}),
    re.compile(r"The target Jammed your attack"): (ChatType.DODGE, CombatRow, {"miss": True}),
    re.compile(r"You took (\d+\.\d+) points of damage"): (ChatType.DAMAGE, BaseChatRow, {}),
    re.compile(r"You have gained (\d+\.\d+) experience in your ([a-zA-Z ]+) skill"): (ChatType.SKILL, SkillRow, {}),
    re.compile(r"You have gained (\d+\.\d+) ([a-zA-Z ]+)"): (ChatType.SKILL, SkillRow, {}),
    re.compile(r"Your ([a-zA-Z ]+) has improved by (\d+\.\d+)"): (ChatType.SKILL, SkillRow, {}),
    re.compile(r"Your enhancer ([a-zA-Z0-9 ]+) on your .* broke."): (ChatType.ENHANCER, EnhancerBreakages, {}),
    re.compile(r"You received (.*) x \((\d+)\) Value: (\d+(?:\.\d+)?) PED"): (ChatType.LOOT, LootInstance, {})
}

GLOBAL_REGEXES = {
    re.compile(r"([\w\s\'\(\)]+) killed a creature \(([\w\s\(\),]+)\) with a value of (\d+) PED! A record has been added to the Hall of Fame!"): (ChatType.GLOBAL, GlobalInstance, {"hof": True}),
    re.compile(r"([\w\s\'\(\)]+) killed a creature \(([\w\s\(\),]+)\) with a value of (\d+) PED!"): (ChatType.GLOBAL, GlobalInstance, {}),
    re.compile(r"([\w\s\'\(\)]+) constructed an item \(([\w\s\(\),]+)\) worth (\d+) PED! A record has been added to the Hall of Fame!"): (ChatType.GLOBAL, GlobalInstance, {"hof": True}),
    re.compile(r"([\w\s\'\(\)]+) constructed an item \(([\w\s\(\),]+)\) worth (\d+) PED!"): (ChatType.GLOBAL, GlobalInstance, {}),
    re.compile(r"([\w\s\'\(\)]+) found a deposit \(([\w\s\(\)]+)\) with a value of (\d+) PED! A record has been added to the Hall of Fame!"): (ChatType.GLOBAL, GlobalInstance, {"hof": True}),
    re.compile(r"([\w\s\'\(\)]+) found a deposit \(([\w\s\(\)]+)\) with a value of (\d+) PED!"): (ChatType.GLOBAL, GlobalInstance, {}),
    re.compile(r"([\w\s\'\(\)]+) killed a creature \(([\w\s\(\),]+)\) with a value of (\d+) PED at ([\s\w\W]+)!"): (ChatType.GLOBAL, GlobalInstance, {}),
}


class ChatReader(object):

    def __init__(self, app):
        self.app = app
        self.lines = queue.Queue(maxsize=MAX_QUEUED_CHAT_ROWS)
        self.reader = None
        self._stop_event = None
        self._reader_path = None
        self._retry_after = 0
        self._ready_event = threading.Event()
        self.last_error = None

    def delay_start_reader(self):
        configured_path = self.app.config.location.value
        path = (
            os.path.abspath(os.path.expanduser(configured_path))
            if configured_path else None
        )

        if path != self._reader_path:
            if not self.stop_reader():
                return
            self._reader_path = path
            self._retry_after = 0
            self.last_error = None

        if not path:
            return

        if self.reader and self.reader.is_alive():
            return

        if time.monotonic() < self._retry_after:
            return

        stop_event = threading.Event()
        self._stop_event = stop_event
        self._ready_event.clear()
        self.reader = threading.Thread(
            target=self.readlines,
            args=(path, stop_event),
            daemon=True,
            name="ChatReader"
        )
        self.reader.start()

    def stop_reader(self, clear_pending=True):
        if self._stop_event:
            self._stop_event.set()

        reader = self.reader
        if reader and reader is not threading.current_thread():
            reader.join(timeout=1)

        if reader and reader.is_alive():
            logger.warning("Chat reader did not stop within one second")
            return False

        self.reader = None
        self._stop_event = None
        self._reader_path = None
        if clear_pending:
            self._clear_pending_lines()
        return True

    def readlines(self, path, stop_event):
        try:
            with open(path, "r", encoding="utf_8_sig", errors="replace") as source:
                source.seek(0, os.SEEK_END)
                self.last_error = None
                self._ready_event.set()
                pending_line = ""
                while not stop_event.is_set():
                    line = source.readline()
                    if not line:
                        stop_event.wait(CHAT_POLL_INTERVAL)
                        continue
                    pending_line += line
                    if pending_line.endswith("\n"):
                        self._parse_chat_line(pending_line, stop_event)
                        pending_line = ""
        except OSError as exc:
            if not stop_event.is_set():
                self.last_error = str(exc)
                logger.error("Unable to read chat log %s: %s", path, exc)
        finally:
            if not stop_event.is_set():
                self._retry_after = time.monotonic() + READER_RETRY_DELAY

    def _parse_chat_line(self, line, stop_event):
        log_line = parse_log_line(line)
        if log_line.channel == "System":
            patterns = REGEXES
        elif log_line.channel == "Globals":
            patterns = GLOBAL_REGEXES
        else:
            return

        for rx, (chat_type, chat_cls, kwargs) in patterns.items():
            match = rx.search(log_line.msg)
            if not match:
                continue
            try:
                chat_instance = chat_cls(*match.groups(), **kwargs)
                chat_instance.time = datetime.strptime(
                    log_line.time, "%Y-%m-%d %H:%M:%S"
                )
            except (InvalidOperation, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed chat event: %s", exc)
                return

            self._enqueue(chat_instance, stop_event)
            return

    def _enqueue(self, chat_instance, stop_event):
        while not stop_event.is_set():
            try:
                self.lines.put(chat_instance, timeout=CHAT_POLL_INTERVAL)
                return
            except queue.Full:
                continue

    def _clear_pending_lines(self):
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                return

    def getlines(self, limit):
        if limit < 0:
            raise ValueError("Line limit must be non-negative")
        lines = []
        for _ in range(limit):
            try:
                lines.append(self.lines.get_nowait())
            except queue.Empty:
                break
        return lines

    def getline(self):
        try:
            return self.lines.get_nowait()
        except queue.Empty:
            return None
