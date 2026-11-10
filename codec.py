"""Кодирование входной машины в слово и разбор стабильных конфигураций.

Ни поиска команд, ни симуляции здесь нет — только перевод в обе стороны.
"""
from dataclasses import dataclass
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
TAPE = "01_"


@dataclass(frozen=True)
class Transition:
    source: int
    read: str
    target: int
    write: str
    move: str


@dataclass(frozen=True)
class Machine:
    start: int
    transitions: tuple[Transition, ...]
    name: str = "unnamed"

    def validate(self):
        if type(self.start) is not int or self.start < 1:
            raise ValueError("номера состояний — положительные целые")
        keys = set()
        for t in self.transitions:
            for q in (t.source, t.target):
                if type(q) is not int or q < 1:
                    raise ValueError("номера состояний — положительные целые")
            if t.read not in tuple(TAPE) or t.write not in tuple(TAPE):
                raise ValueError("на ленте только символы 0, 1, _")
            if t.move not in ("L", "R", "S"):
                raise ValueError("движение может быть L, R или S")
            if (t.source, t.read) in keys:
                raise ValueError("повторная команда для (source, read): машина не детерминирована")
            keys.add((t.source, t.read))

    def to_dict(self):
        return {"name": self.name, "start": self.start,
                "transitions": [t.__dict__ for t in self.transitions]}


def load_machine(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    machine = Machine(data["start"], tuple(Transition(**t) for t in data["transitions"]),
                      data.get("name", "unnamed"))
    machine.validate()
    return machine


def controls():
    return json.loads((ROOT / "controls.json").read_text(encoding="utf-8"))


def encode_program(machine):
    machine.validate()
    return "".join(";" + "u" * t.source + t.read + "u" * t.target + t.write + t.move
                   for t in machine.transitions)


@dataclass(frozen=True)
class Snapshot:
    state: int
    left: str
    scanned: str
    right: str

    @property
    def window(self):
        return self.left + self.scanned + self.right

    @property
    def head_index(self):
        return len(self.left)

    def human(self):
        return f"q{self.state}  {self.left}[{self.scanned}]{self.right}"


def encode_snapshot(machine, snapshot):
    if type(snapshot.state) is not int or snapshot.state < 1:
        raise ValueError("номер состояния — положительное целое")
    if len(snapshot.scanned) != 1 or set(snapshot.window) - set(TAPE):
        raise ValueError("плохая лента")
    return (controls()["READY"] + "^" + encode_program(machine) + "#" +
            "u" * snapshot.state + "[" + snapshot.left + "@" + snapshot.scanned +
            snapshot.right + "]")


def encode(machine, word):
    if set(word) - set("01"):
        raise ValueError("входное слово должно быть двоичным (пустое можно)")
    tape = word or "_"
    return encode_snapshot(machine, Snapshot(machine.start, "", tape[0], tape[1:]))


def decode_stable(word, ready=None):
    ready = controls()["READY"] if ready is None else ready
    if not (word.startswith(ready + "^") or word.startswith("!^")):
        raise ValueError("это не стабильная и не заключительная конфигурация")
    _, config = word.split("#")
    state, tape = config.split("[")
    if not state or set(state) != {"u"} or not tape.endswith("]"):
        raise ValueError("не удалось разобрать состояние или ленту")
    left, right = tape[:-1].split("@")
    if not right or set(left + right) - set(TAPE):
        raise ValueError("не удалось разобрать ленту")
    return Snapshot(len(state), left, right[0], right[1:])


def readable(word, names=None):
    names = controls() if names is None else names
    aliases = {v: "⟨" + k + "⟩" for k, v in names.items()}
    return "".join(aliases.get(c, c) for c in word)
