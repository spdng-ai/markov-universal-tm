"""Строит ОДИН фиксированный конечный нормальный алгоритм Маркова.

Входной машины здесь нет и быть не может: каждое имя вроде ⟨READY⟩ — одна
конкретная буква Юникода, а не переменная. Все циклы ниже идут по постоянным
конечным алфавитам. Авторитетный результат — развёрнутый упорядоченный
список в rules.json.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
from engine import Rule

TAPE = "01_"
DIRECTIONS = "LRS"
DATA = "^;#u01_LRS[@]xvy:!"


def build():
    controls = {}
    rules = []
    group = ""

    def Q(name):
        if name not in controls:
            controls[name] = chr(0xE000 + len(controls))
        return controls[name]

    def add(lhs, rhs, terminal=False):
        rules.append(Rule(lhs, rhs, terminal, group))

    def right(name, stop):
        # ровно len(DATA) - len(stop) буквальных правил, в порядке алфавита DATA
        for c in DATA:
            if c not in stop:
                add(Q(name) + c, c + Q(name))

    def left(name, stop, restore=None):
        restore = {} if restore is None else restore
        for c in DATA:
            if c not in stop:
                add(c + Q(name), Q(name) + restore.get(c, c))

    group = "01 read scanned symbol"
    add(Q("READY") + "^", "^" + Q("TO_HEAD"))
    right("TO_HEAD", "@")
    add(Q("TO_HEAD") + "@", "@" + Q("READ"))

    # три ветви помнят только прочитанный символ (0, 1 или _) — и всё
    for a in TAPE:
        name = lambda stem: stem + "_" + a
        group = "02 rewind and choose record " + a
        add(Q("READ") + a, Q(name("REWIND")) + a)
        left(name("REWIND"), "^")
        add("^" + Q(name("REWIND")), "^" + Q(name("FIND")))
        add(Q(name("FIND")) + ";", ":" + Q(name("CMP")))
        add(Q(name("FIND")) + "#", Q("HALT_BACK") + "#")

        group = "03 compare unary source " + a
        add(Q(name("CMP")) + "x", "x" + Q(name("CMP")))
        add(Q(name("CMP")) + "u", "x" + Q(name("TO_STATE")))
        right(name("TO_STATE"), "#")
        add(Q(name("TO_STATE")) + "#", "#" + Q(name("CHECK")))
        add(Q(name("CHECK")) + "v", "v" + Q(name("CHECK")))
        add(Q(name("CHECK")) + "u", "v" + Q(name("BACK")))
        add(Q(name("CHECK")) + "[", Q(name("FAIL_RIGHT")) + "[")
        left(name("BACK"), ":")
        add(":" + Q(name("BACK")), ":" + Q(name("CMP")))
        for b in TAPE:
            target = "END_TO_STATE" if a == b else "FAIL_RIGHT"
            add(Q(name("CMP")) + b, Q(name(target)) + b)
        right(name("END_TO_STATE"), "#")
        add(Q(name("END_TO_STATE")) + "#", "#" + Q(name("CHECK_END")))
        add(Q(name("CHECK_END")) + "v", "v" + Q(name("CHECK_END")))
        add(Q(name("CHECK_END")) + "u", Q(name("FAIL_RIGHT")) + "u")
        add(Q(name("CHECK_END")) + "[", Q("DELETE_STATE") + "[")

        group = "04 reject restore and skip " + a
        right(name("FAIL_RIGHT"), "[")
        add(Q(name("FAIL_RIGHT")) + "[", Q(name("FAIL_LEFT")) + "[")
        left(name("FAIL_LEFT"), "^", {"x": "u", "v": "u"})
        add("^" + Q(name("FAIL_LEFT")), "^" + Q(name("FIND_MARK")))
        right(name("FIND_MARK"), ":")
        add(Q(name("FIND_MARK")) + ":", ";" + Q(name("SKIP")))
        right(name("SKIP"), ";#")
        for end in ";#":
            add(Q(name("SKIP")) + end, Q(name("FIND")) + end)

    group = "05 erase old state and copy target"
    add("v" + Q("DELETE_STATE"), Q("DELETE_STATE"))
    add("#" + Q("DELETE_STATE"), Q("SEEK_CAND") + "#")
    left("SEEK_CAND", ":", {"x": "u"})
    add(":" + Q("SEEK_CAND"), ":" + Q("SKIP_SOURCE"))
    add(Q("SKIP_SOURCE") + "u", "u" + Q("SKIP_SOURCE"))
    for a in TAPE:
        add(Q("SKIP_SOURCE") + a, a + Q("COPY"))
    add(Q("COPY") + "y", "y" + Q("COPY"))
    add(Q("COPY") + "u", "y" + Q("COPY_TO_STATE"))
    right("COPY_TO_STATE", "[")
    add(Q("COPY_TO_STATE") + "[", "u" + Q("COPY_BACK") + "[")
    left("COPY_BACK", ":")
    add(":" + Q("COPY_BACK"), ":" + Q("SKIP_SOURCE"))

    group = "06 read action and write scanned cell"
    for b in TAPE:
        add(Q("COPY") + b, b + Q("DIR_" + b))
        for d in DIRECTIONS:
            seek = "WRITE_SEEK_" + b + d
            write = "WRITE_" + b + d
            add(Q("DIR_" + b) + d, d + Q(seek))
            right(seek, "@")
            add(Q(seek) + "@", "@" + Q(write))
            for old in TAPE:
                if d == "R":
                    replacement = b + "@" + Q("EXTEND_R")
                elif d == "L":
                    replacement = Q("MOVE_L") + "@" + b
                else:
                    replacement = "@" + Q("CLEAN") + b
                add("@" + Q(write) + old, replacement)

    group = "07 move head and extend tape"
    for c in TAPE:
        add(Q("EXTEND_R") + c, Q("CLEAN") + c)
    add(Q("EXTEND_R") + "]", Q("CLEAN") + "_]")
    for c in TAPE:
        add(c + Q("MOVE_L") + "@", Q("CLEAN") + "@" + c)
    add("[" + Q("MOVE_L") + "@", "[" + Q("CLEAN") + "@_")

    group = "08 restore program and finish transition"
    left("CLEAN", "^", {"y": "u", ":": ";"})
    add("^" + Q("CLEAN"), Q("READY") + "^")

    group = "09 terminate on missing transition"
    left("HALT_BACK", "^")
    add("^" + Q("HALT_BACK"), "!^", terminal=True)

    # статические проверки самой таблицы; к входной машине отношения не имеют
    symbols = set(controls.values())
    assert len(DATA) == len(set(DATA))
    assert not symbols.intersection(DATA)
    assert len({r.lhs for r in rules}) == len(rules)
    assert sum(r.terminal for r in rules) == 1
    for r in rules:
        assert r.lhs and sum(c in symbols for c in r.lhs) == 1
        assert sum(c in symbols for c in r.rhs) == (0 if r.terminal else 1)
        assert set(r.lhs + r.rhs) <= set(DATA) | symbols
    assert {c for r in rules for c in r.lhs if c in symbols} == symbols
    return tuple(rules), controls


def export(directory):
    rules, controls = build()
    directory = Path(directory)
    blob = json.dumps([r.__dict__ for r in rules], ensure_ascii=True, indent=2) + "\n"
    (directory / "rules.json").write_text(blob, encoding="utf-8")
    (directory / "controls.json").write_text(
        json.dumps(controls, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    alias = {v: "⟨" + k + "⟩" for k, v in controls.items()}
    show = lambda s: "".join(alias.get(c, c) for c in s)
    lines = ["Каждое ⟨ИМЯ⟩ обозначает ОДНУ букву. Порядок строк — приоритет.",
             "→· — заключительная замена. Исполняемые строки — в rules.json.", ""]
    previous = None
    for i, rule in enumerate(rules, 1):
        if rule.group != previous:
            lines.append("\n# " + rule.group)
            previous = rule.group
        lines.append(f"{i:04d}  {show(rule.lhs)} {'→·' if rule.terminal else '→'} {show(rule.rhs)}")
    (directory / "rules_readable.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    info = {
        "rules": len(rules), "control_letters": len(controls),
        "data_letters": len(DATA), "alphabet_size": len(DATA) + len(controls),
        "terminal_rules": sum(r.terminal for r in rules),
        "rules_json_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        "groups": dict(Counter(r.group for r in rules)),
        "data_alphabet": DATA,
    }
    (directory / "rules_info.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


if __name__ == "__main__":
    print(json.dumps(export(Path(__file__).parent), indent=2))
