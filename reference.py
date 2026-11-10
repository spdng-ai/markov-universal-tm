"""Обычный симулятор МТ; используется только verify.py для сверки.

Лента — словарь «целая координата → символ», переходы — прямой словарь.
Про правила Маркова модуль ничего не знает и слово интерпретатора не трогает.
"""
from codec import Snapshot


class ReferenceTM:
    def __init__(self, machine, word="", snapshot=None):
        self.delta = {(t.source, t.read): (t.target, t.write, t.move)
                      for t in machine.transitions}
        if snapshot is None:
            tape = word or "_"
            snapshot = Snapshot(machine.start, "", tape[0], tape[1:])
        self.state = snapshot.state
        self.head = len(snapshot.left)
        self.lo, self.hi = 0, len(snapshot.window) - 1
        self.tape = {i: c for i, c in enumerate(snapshot.window) if c != "_"}
        self.steps = 0

    def step(self):
        instruction = self.delta.get((self.state, self.tape.get(self.head, "_")))
        if instruction is None:
            return False
        target, written, move = instruction
        if written == "_":
            self.tape.pop(self.head, None)
        else:
            self.tape[self.head] = written
        self.state = target
        self.head += {"L": -1, "S": 0, "R": 1}[move]
        self.lo = min(self.lo, self.head)
        self.hi = max(self.hi, self.head)
        self.steps += 1
        return True

    def snapshot(self):
        return Snapshot(
            self.state,
            "".join(self.tape.get(i, "_") for i in range(self.lo, self.head)),
            self.tape.get(self.head, "_"),
            "".join(self.tape.get(i, "_") for i in range(self.head + 1, self.hi + 1)),
        )
