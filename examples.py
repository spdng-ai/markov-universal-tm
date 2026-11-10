"""Примеры входных машин. Правила Маркова этот модуль не строит."""
from pathlib import Path
import json
from codec import Machine, Transition as T, encode


def examples():
    return {
        "invert": Machine(1, (T(1, "0", 1, "1", "R"),
                              T(1, "1", 1, "0", "R")), "Инверсия битов"),
        "increment": Machine(1, (
            T(1, "0", 1, "0", "R"), T(1, "1", 1, "1", "R"),
            T(1, "_", 2, "_", "L"), T(2, "1", 2, "0", "L"),
            T(2, "0", 3, "1", "S"), T(2, "_", 3, "1", "S")), "Двоичное +1"),
        "walk": Machine(1, tuple(
            T(q, a, q + 1, written, move)
            for q, written, move in ((1, "1", "L"), (2, "0", "L"),
                                     (3, "1", "R"), (4, "1", "R"),
                                     (5, "0", "R"), (6, "1", "R"), (7, "0", "L"))
            for a in "01_"), "Выход за обе границы"),
        "immediate": Machine(1, (), "Немедленная остановка"),
        "long_states": Machine(129, (T(129, "0", 257, "1", "R"),
                                    T(257, "_", 65, "0", "L")), "Длинные коды"),
        "loop_stay": Machine(1, (T(1, "_", 1, "_", "S"),), "Бесконечное S"),
        "loop_right": Machine(1, tuple(T(1, a, 1, a, "R") for a in "01_"),
                              "Бесконечное R"),
    }


def write_examples():
    directory = Path(__file__).parent / "examples"
    directory.mkdir(exist_ok=True)
    machines = examples()
    for name, machine in machines.items():
        (directory / (name + ".json")).write_text(
            json.dumps(machine.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (directory / "invert_01011.word").write_text(encode(machines["invert"], "01011") + "\n",
                                               encoding="utf-8")


if __name__ == "__main__":
    write_examples()
    print("Записал examples/*.json и закодированное слово invert_01011.word")
