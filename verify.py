"""Воспроизводимые дифференциальные проверки; все запуски НАМ — один и тот же набор Rule.

Эталонная МТ продвигается на шаг только после стабильной границы НАМ.
Она ничего не подсказывает вычислению и слово интерпретатора не меняет.
Главные действующие лица — задачи 1.1–1.14 практикума (Тихомирова,
Сафоненко, гл. 1): каждая прогоняется целиком, результат сверяется и с
обычным симулятором, и с ожидаемым ответом из условия задачи.
"""
from pathlib import Path
from itertools import product
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import random
import sys
import time

from engine import Markov, Rule, load_rules
from fixed_rules import build
from codec import (Machine, Transition as T, Snapshot, controls, encode, encode_program,
                   encode_snapshot, decode_stable)
from examples import examples
from reference import ReferenceTM

ROOT = Path(__file__).parent

OMEGA = 20    # Ω — нормальная остановка в задачах практикума
OMEGA_ERROR = 21  # Ω1 — остановка из-за ошибки входа

# (ключ examples, вход, ожидаемая лента без внешних _, ожидаемое состояние)
TASK_CASES = [
    ("task_1_01", "σbaba", "σbbbb", OMEGA),
    ("task_1_01", "σab", "σbb", OMEGA),
    ("task_1_02", "σ01001", "σ010011", OMEGA),
    ("task_1_02", "σ", "σ1", OMEGA_ERROR),
    ("task_1_03", "σ01010", "σ010100", OMEGA),
    ("task_1_03", "σ1", "σ11", OMEGA),
    ("task_1_04", "σ011", "σ0111", OMEGA),
    ("task_1_04", "σ01010", "σ010100", OMEGA),
    ("task_1_05", "σ100121101201", "σ10***11***01", OMEGA),
    ("task_1_05", "σ12", "σ12", OMEGA),
    ("task_1_06", "σ111", "σ11", OMEGA),
    ("task_1_06", "σ11", "σ1", OMEGA),
    ("task_1_06", "σ1", "σ1", OMEGA_ERROR),
    ("task_1_07", "σ1010", "σ1010*0101", OMEGA),
    ("task_1_07", "σ01", "σ01*10", OMEGA),
    ("task_1_08", "σ1010", "σ10100101", OMEGA),
    ("task_1_08", "σ0", "σ00", OMEGA),
    ("task_1_09", "σ100", "σ100*100", OMEGA),
    ("task_1_09", "σ10", "σ10*10", OMEGA),
    ("task_1_10", "σ100", "σ100100", OMEGA),
    ("task_1_10", "σ01", "σ0101", OMEGA),
    ("task_1_11", "σ0011", "σ1100", OMEGA),
    ("task_1_11", "σ0111", "σ1110", OMEGA),
    ("task_1_11", "σ010", "σ010", OMEGA),
    ("task_1_12", "σ010", "σ010", OMEGA),
    ("task_1_12", "σ0110", "σ0110", OMEGA),
    ("task_1_12", "σ011", "σ011", OMEGA_ERROR),
    ("task_1_12", "σ0100", "σ0100", OMEGA_ERROR),
    ("task_1_13", "σ11∸1", "σ11", OMEGA),
    ("task_1_13", "σ111∸11", "σ11", OMEGA),
    ("task_1_13", "σ11∸111", "σ1", OMEGA),
    ("task_1_13", "σ1111∸11", "σ111", OMEGA),
    ("task_1_13", "σ11∸11", "σ1", OMEGA),
    ("task_1_13", "σ1111∸1111", "σ1", OMEGA),
    ("task_1_13", "σ11", "σ11", OMEGA_ERROR),
    ("task_1_14", "σ0101", "σ0101=", OMEGA),
    ("task_1_14", "σ011", "σ011+", OMEGA),
    ("task_1_14", "σ0001", "σ0001-", OMEGA),
    ("task_1_14", "σ1100", "σ1100=", OMEGA),
    ("task_1_14", "σ1", "σ1+", OMEGA),
    ("task_1_14", "σ0", "σ0-", OMEGA),
    ("task_1_14", "σ", "σ", OMEGA_ERROR),
]


def check_engine():
    # приоритет правила важнее позиции вхождения в слове
    priority = Markov([Rule("a", "b"), Rule("ba", "c")], alphabet_filter=False)
    assert priority.step("ba").word == "bb"
    assert priority.step("aaa").word == "baa"  # самое левое вхождение
    # после срабатывания правила 2 поиск снова начинается с правила 1
    restarted = Markov([Rule("b", "c", True), Rule("a", "b")]).run("a", 10)
    assert (restarted.word, restarted.replacements, restarted.status) == ("c", 2, "terminal")
    terminal = Markov([Rule("a", "aa", True)]).run("a", 100)
    assert (terminal.word, terminal.replacements, terminal.status) == ("aa", 1, "terminal")
    assert Markov([Rule("", "x", True)]).run("abc").word == "xabc"
    assert Markov([Rule("x", "y")]).run("abc").status == "no_rule"
    limited = Markov([Rule("a", "a")]).run("a", 3)
    assert (limited.status, limited.replacements) == ("limit", 3)
    assert Markov([]).run("", 0).status == "limit"

    # независимый полный перебор против индекса по первым буквам
    rng = random.Random(64017)
    replacements = 0
    for _ in range(400):
        literal = lambda: "".join(rng.choice("ab") for _ in range(rng.randrange(4)))
        rules = tuple(Rule(literal(), literal(), rng.random() < 0.15)
                      for _ in range(rng.randint(0, 8)))
        fast, plain = Markov(rules), Markov(rules, alphabet_filter=False)
        word = literal() + literal()
        for _ in range(25):
            x, y = fast.step(word), plain.step(word)
            assert x == y
            if x is None:
                break
            replacements += 1
            word = x.word
            if x.terminal:
                break
    return {"random_rule_sets": 400, "compared_replacements": replacements,
            "semantics_checks": 8}


def main():
    started = time.perf_counter()
    file = ROOT / "rules.json"
    original_bytes = file.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    rules = load_rules(file)
    generated, generated_controls = build()
    assert rules == generated
    names = controls()
    assert names == generated_controls
    ready = names["READY"]
    control_letters = set(names.values())
    info = json.loads((ROOT / "rules_info.json").read_text(encoding="utf-8"))
    engine = Markov(rules)
    plain_engine = Markov(rules, alphabet_filter=False)
    groups, statuses, hits = Counter(), Counter(), Counter()
    cases = total_replacements = total_transitions = audited_replacements = 0
    named_results = []
    engine_checks = check_engine()
    print("Семантика движка и совпадение индекс/полный перебор: OK", flush=True)

    def case(machine, input_word="", *, snapshot=None, bound=15, budget=8000000,
             group="", audit=False, plain=False):
        nonlocal cases, total_replacements, total_transitions, audited_replacements
        word = encode(machine, input_word) if snapshot is None else encode_snapshot(machine, snapshot)
        reference = ReferenceTM(machine, input_word, snapshot)
        program_prefix = "^" + encode_program(machine)
        completed = 0
        assert decode_stable(word, ready) == reference.snapshot()
        interpreter = plain_engine if plain else engine

        def check_boundary():
            assert word[1:word.index("#")] == program_prefix, (machine.name, "program changed")
            assert decode_stable(word, ready) == reference.snapshot(), (
                machine.name, input_word, decode_stable(word, ready), reference.snapshot())

        status = None
        for count in range(1, budget + 1):
            if audit:
                assert sum(c in control_letters for c in word) == 1
                candidates = engine._candidates(frozenset(word))
                applicable = [(i, word.find(rules[i].lhs)) for i in candidates
                              if rules[i].lhs in word]
                assert len(applicable) == 1, ("overlap or deadlock", applicable, word)
                # управляющая буква одна, значит и вхождение одно
                i, position = applicable[0]
                assert word.find(rules[i].lhs, position + 1) == -1
                audited_replacements += 1
            applied = interpreter.step(word)
            assert applied is not None, ("unexpected no_rule", machine.name, repr(word))
            hits[applied.rule_index + 1] += 1
            word = applied.word
            if applied.terminal:
                assert not reference.step(), ("premature halt", machine.name)
                assert word.startswith("!^")
                check_boundary()
                status = "terminal"
                break
            if word.startswith(ready + "^"):
                assert reference.step(), ("extra TM transition", machine.name)
                completed += 1
                check_boundary()
                if completed >= bound:
                    status = "transition_limit"
                    break
        assert status is not None, ("NAM replacement budget exhausted during a checked case",
                                    machine.name, input_word, completed, budget)
        cases += 1
        groups[group] += 1
        statuses[status] += 1
        total_replacements += count
        total_transitions += completed
        return {"machine": machine.name, "input": input_word, "status": status,
                "tm_transitions": completed, "nam_replacements": count,
                "configuration": reference.snapshot().__dict__}

    ex = examples()

    # Задачи 1.1–1.14 практикума: полный прогон, сверка с эталоном и условием
    for key, word, expected_tape, expected_state in TASK_CASES:
        result = case(ex[key], word, group="practicum_tasks_1_1_to_1_14", bound=200)
        assert result["status"] == "terminal", (key, word, result["status"])
        s = result["configuration"]
        display = (s["left"] + s["scanned"] + s["right"]).strip("_")
        assert display == expected_tape, (key, word, display, expected_tape)
        assert s["state"] == expected_state, (key, word, s["state"], expected_state)
    print(f"Задачи 1.1–1.14 практикума: {len(TASK_CASES)} прогонов, результаты совпали "
          f"с обычным симулятором и условиями: OK", flush=True)

    # служебные демо
    for key, word in (("invert", "01011"), ("invert", ""), ("immediate", ""),
                      ("immediate", "101")):
        named_results.append(case(ex[key], word, group="service_demos", bound=30))
    assert named_results[0]["configuration"] == Snapshot(1, "10100", "_", "").__dict__
    print("Служебные демо (инверсия, мгновенная остановка, пустой вход): OK", flush=True)

    # все двоичные слова длины 0..3: инверсия и задача 1.2 (дописать 1)
    for length in range(4):
        for bits in product("01", repeat=length):
            word = "".join(bits)
            result = case(ex["invert"], word, group="all_binary_words_length_0_to_3", bound=30)
            assert result["status"] == "terminal"
            s = result["configuration"]
            display = (s["left"] + s["scanned"] + s["right"]).strip("_")
            assert display == "".join("1" if c == "0" else "0" for c in word), (word, display)
            word2 = "σ" + word
            result = case(ex["task_1_02"], word2, group="all_binary_words_length_0_to_3",
                          bound=30)
            assert result["status"] == "terminal"
            s = result["configuration"]
            display = (s["left"] + s["scanned"] + s["right"]).strip("_")
            if word:
                assert display == word2 + "1" and s["state"] == OMEGA, (word2, display)
            else:
                assert display == "σ1" and s["state"] == OMEGA_ERROR, (word2, display)
    print("Все 15 двоичных слов длины 0..3 для инверсии и задачи 1.2: OK", flush=True)

    # все сочетания чтения/записи/движения и соседей с обеих сторон
    for a, b, d, left, right in product("01_", "01_", "LRS", ("", "0", "1", "_"),
                                       ("", "0", "1", "_")):
        machine = Machine(2, (T(2, a, 5, b, d),), "local transition")
        result = case(machine, snapshot=Snapshot(2, left, a, right),
                      group="exhaustive_local_actions", audit=True)
        assert result["status"] == "terminal" and result["tm_transitions"] == 1
    print("432 локальных действия, все движения, записи и соседи; правила единственны: OK", flush=True)

    # записи, дающие несовпадение по длине кода и по символу чтения
    distractors = (T(1, "0", 7, "1", "L"), T(3, "0", 7, "1", "L"),
                   T(2, "1", 7, "1", "L"))
    selected = T(2, "0", 4, "1", "S")
    rng = random.Random(20261005)
    for present in (False, True):
        for _ in range(12):
            rows = list(distractors + ((selected,) if present else ()))
            rng.shuffle(rows)
            result = case(Machine(2, tuple(rows), "lookup ordering"), "0",
                          group="lookup_and_program_order", audit=True)
            assert result["tm_transitions"] == int(present)
    # те же примеры полным перебором, совсем без оптимизации
    for key, word in (("invert", "01"), ("task_1_02", "σ1"), ("immediate", "")):
        case(ex[key], word, group="full_ordered_scan", plain=True)
    print("Отсутствующие команды, все виды несовпадения, перемешанные программы, полный перебор: OK",
          flush=True)

    # все 10^3 частичных таблиц одного рабочего состояния; пустой вход.
    options = (None,) + tuple(product("01_", "LRS"))
    for choices in product(options, repeat=3):
        rows = tuple(T(1, a, 1, choice[0], choice[1]) for a, choice in zip("01_", choices)
                     if choice is not None)
        machine = Machine(1, rows, "exhaustive one-state table")
        case(machine, "", bound=4, group="all_1000_one_state_tables")
    print("Все 1000 таблиц одного состояния, префиксы до 4 переходов: OK", flush=True)

    for i in range(60):
        ids = rng.sample(range(1, 10), rng.randint(1, 5))
        rows = [T(q, a, rng.choice(ids), rng.choice("01_"), rng.choice("LRS"))
                for q in ids for a in "01_" if rng.random() < 0.72]
        rng.shuffle(rows)
        machine = Machine(rng.choice(ids), tuple(rows), "random_" + str(i))
        word = "".join(rng.choice("01") for _ in range(rng.randrange(6)))
        case(machine, word, bound=12, group="seeded_random_multi_state")
    print("60 случайных машин с фиксированным seed: OK", flush=True)

    for key, word in (("loop_stay", ""), ("loop_right", "0110")):
        result = case(ex[key], word, bound=80, group="infinite_machine_prefixes")
        assert result["status"] == "transition_limit"
        named_results.append(result)
    left_loop = Machine(1, (T(1, "_", 1, "_", "L"),), "Infinite left extension")
    case(left_loop, "", bound=80, group="infinite_machine_prefixes")
    interrupted = engine.run(encode(ex["loop_stay"], ""), 17)
    assert interrupted.status == "limit" and interrupted.replacements == 17
    # пауза и продолжение не меняют вычисление, даже в середине фазы
    resumed = engine.run(interrupted.word, 53)
    continuous = engine.run(encode(ex["loop_stay"], ""), 70)
    assert resumed.word == continuous.word and resumed.status == continuous.status == "limit"
    assert file.read_bytes() == original_bytes
    assert tuple(engine.rules) == rules == tuple(plain_engine.rules)

    report = {
        "status": "PASS", "finished_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "elapsed_seconds": round(time.perf_counter() - started, 3),
        "rules": len(rules), "alphabet_size": info["alphabet_size"],
        "rules_json_sha256": original_hash,
        "cases": cases, "compared_tm_transitions": total_transitions,
        "compared_stable_configurations_including_initial": cases + total_transitions,
        "executed_nam_replacements_in_differential_cases": total_replacements,
        "audited_unique_rule_and_occurrence_replacements": audited_replacements,
        "case_statuses": dict(statuses), "case_groups": dict(groups),
        "named_results": named_results, "generic_engine": engine_checks,
        "distinct_rules_exercised": len(hits),
        "exercised_rule_numbers": sorted(hits),
        "limitations": [
            "Конечные тесты не доказывают универсальность и расходимость.",
            "transition_limit и limit означают только прерванную проверку.",
            "Широкие проходные правила для недостижимых контекстов могли не сработать.",
            "Предусловие — корректно кодированные детерминированные машины.",
        ],
    }
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "status", "elapsed_seconds", "cases", "compared_tm_transitions",
        "executed_nam_replacements_in_differential_cases", "case_statuses",
        "distinct_rules_exercised", "rules_json_sha256")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
