#!/usr/bin/env python3
"""Универсальный нормальный алгоритм Маркова — приложение.

Запуск без аргументов показывает, что это за проект, и сразу гоняет
демонстрацию на нескольких машинах Тьюринга. Подробности: python3 app.py --help
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time

# Windows-консоль по умолчанию может быть не в UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import Markov, load_rules                      # noqa: E402
from codec import (controls, encode, decode_stable,         # noqa: E402
                   load_machine, readable)

ABOUT = """\
ОДИН УНИВЕРСАЛЬНЫЙ НОРМАЛЬНЫЙ АЛГОРИТМ МАРКОВА
симулятор любой машины Тьюринга, записанный как 6962 правил замены

ЧТО ЭТО ЗА ПРОЕКТ
  Нормальный алгоритм Маркова (НАМ) — одна из классических моделей
  вычислений. У него нет ни переменных, ни циклов, ни головки: есть только
  упорядоченный список правил вида «подстрока → подстрока» и строка-слово.
  На каждом шаге берётся ПЕРВОЕ по порядку правило, левая часть которого
  встречается в слове, и самое левое вхождение заменяется. Правило с
  пометкой «заключительное» останавливает работу.

  Проект доказывает и показывает на практике, что такой простой механизм
  универсален: построен ОДИН фиксированный набор из 6962 правил (алфавит
  348 букв), который выполняет программу ЛЮБОЙ детерминированной машины
  Тьюринга, записанной прямо в входном слове. Правила не меняются при
  смене машины — меняется только входное слово.

КАК ЭТО УСТРОЕНО
  Вход:    <READY>^ПРОГРАММА # u^q [ лента с @ перед ячейкой под головкой ]
           • команда машины δ(q,a)=(p,b,D) кодируется как  ;u^q a u^p b D
             (состояние номер q — это q букв «u», поэтому число состояний
             не ограничено размером алфавита);
           • в слове есть ровно одна управляющая буква-«курсор»; она ходит
             по слову обычными заменами.
  Один шаг машины Тьюринга = последовательность замен Маркова:
    1. дойти до головки и прочитать символ под ней (одна из 16 букв ленты);
    2. вернуться к началу программы и перебрать записи команд;
    3. сравнить унарные коды состояний попарной разметкой букв u → x / v;
    4. при несовпадении — восстановить разметку и взять следующую запись;
    5. при совпадении — стереть старое состояние, скопировать новое (u → y);
    6. записать символ, сдвинуть головку (при необходимости дописать «_»);
    7. восстановить программу и вернуть <READY> — шаг завершён.
  Если подходящей команды нет, срабатывает единственное заключительное
  правило — машина остановилась, результат остаётся в слове.

  Ленточный алфавит — рабочие символы задач практикума (Тихомирова,
  Сафоненко, гл. 1): 0 1 2 a b * ∸ + - = и помеченные символы c d e f
  (= 0' 1' 0'' 1''); σ — маркер начала ленты; _ — пустая ячейка.
  В задачах Ω = состояние 20 (нормальная остановка), Ω1 = 21 (ошибка).

ЧТО ЗДЕСЬ ЧТО
  rules.json          — сами 6962 правил (то, что выполняет вычисление)
  rules_readable.txt  — те же правила с понятными именами управляющих букв
  engine.py           — общий интерпретатор замен (ничего не знает о МТ)
  codec.py            — запись машины и входа в слово; чтение результата
  examples/*.json     — задачи практикума 1.1–1.14 + служебные демо
  reference.py        — обычный симулятор МТ, нужен ТОЛЬКО для сверки
  verify.py           — полный набор дифференциальных проверок
"""

FORMAT_HELP = """\
Формат своей машины (JSON):
  {"name": "Моя машина", "start": 1,
   "transitions": [
     {"source": 1, "read": "0", "target": 1, "write": "1", "move": "R"}
   ]}
  Символы ленты: 0 1 2 a b * ∸ + - = c d e f σ _
  (c d e f — помеченные символы 0' 1' 0'' 1''; σ — маркер начала ленты;
  _ — пустая ячейка); движение: L, R, S (на месте); номера состояний —
  любые положительные целые; для пары (source, read) — не более одной
  команды; состояние без команд = остановка.
"""

MOVES = {"L": "влево", "R": "вправо", "S": "на месте"}

# (файл, вход, пояснение, бюджет замен) — задачи практикума 1.1–1.14
DEMOS = [
    ("task_1_01.json", "σbaba", "Задача 1.1: заменить все «a» на «b» (σbaba → σbbbb).", 2_000_000),
    ("task_1_02.json", "σ01001", "Задача 1.2: дописать 1 в конец слова (пустое слово — Ω1).", 3_000_000),
    ("task_1_05.json", "σ100121101201", "Задача 1.5: заменить каждую комбинацию «012» на «***».", 4_000_000),
    ("task_1_07.json", "σ1010", "Задача 1.7: скопировать слово в обратном порядке после «*».", 4_000_000),
    ("task_1_11.json", "σ0011", "Задача 1.11: развернуть слово на ленте (σ0011 → σ1100).", 4_000_000),
    ("task_1_12.json", "σ010", "Задача 1.12: палиндром? состояние 20 — да, 21 — нет.", 4_000_000),
    ("task_1_13.json", "σ111∸11", "Задача 1.13: псевдоразность унарных чисел 111∸11 → 11.", 6_000_000),
    ("task_1_14.json", "σ0101", "Задача 1.14: каких символов больше — пишет «+», «-» или «=».", 6_000_000),
]


def describe_machine(machine, limit=12):
    lines = [f"  Машина «{machine.name}», начальное состояние q{machine.start}"]
    if not machine.transitions:
        lines.append("  (команд нет)")
    for t in machine.transitions[:limit]:
        lines.append(f"    q{t.source}, читаем «{t.read}»  →  q{t.target}, пишем «{t.write}», "
                     f"{MOVES[t.move]}")
    if len(machine.transitions) > limit:
        lines.append(f"    … и ещё {len(machine.transitions) - limit} команд (полная таблица в JSON)")
    return "\n".join(lines)


def run_machine(machine, word, *, budget=2_000_000, trace=False, micro=0, plain=False,
                check=True, out=print):
    """Выполняет машину ТОЛЬКО правилами Маркова. Возвращает словарь с итогом."""
    rules = load_rules(ROOT / "rules.json")
    names = controls()
    ready = names["READY"]
    start_word = encode(machine, word)
    transitions = 0
    if trace:
        out("  шаг МТ 0     (замен 0):", decode_stable(start_word, ready).human())

    def observer(count, applied):
        nonlocal transitions
        if count <= micro:
            r = rules[applied.rule_index]
            out(f"    замена {count:>3}, правило №{applied.rule_index + 1:<3}",
                readable(r.lhs, names), "→·" if r.terminal else "→", readable(r.rhs, names))
            out("        слово:", readable(applied.word, names))
        if applied.word.startswith(ready + "^"):
            transitions += 1
            if trace:
                out(f"  шаг МТ {transitions:<5} (замен {count}):",
                    decode_stable(applied.word, ready).human())

    started = time.perf_counter()
    result = Markov(rules, alphabet_filter=not plain).run(start_word, budget, observer)
    elapsed = time.perf_counter() - started
    info = {"status": result.status, "tm_steps": transitions,
            "replacements": result.replacements, "seconds": elapsed,
            "final": None, "tape": None, "reference_match": None}
    if result.status == "terminal":
        snap = decode_stable(result.word, ready)
        info["final"] = snap
        info["tape"] = snap.window.strip("_")
        if check:
            info["reference_match"] = cross_check(machine, word, snap)
    return info


def cross_check(machine, word, snap, limit=100_000):
    """Сверка с обычным симулятором МТ (reference.py). Не влияет на вычисление."""
    from reference import ReferenceTM
    ref = ReferenceTM(machine, word)
    while ref.steps < limit and ref.step():
        pass
    return ref.snapshot() == snap


def print_result(machine, word, info, out=print):
    out(f"  вход: {word!r}" if word else "  вход: (пустое слово)")
    if info["status"] == "terminal":
        out(f"  РЕЗУЛЬТАТ: лента «{info['tape']}», состояние q{info['final'].state}  "
            f"(полная конфигурация: {info['final'].human()})")
        out(f"  шагов машины Тьюринга: {info['tm_steps']}; "
            f"замен Маркова: {info['replacements']:,}; {info['seconds']:.2f} с".replace(",", " "))
        if info["reference_match"] is True:
            out("  сверка с независимым обычным симулятором МТ: СОВПАДАЕТ ✓")
        elif info["reference_match"] is False:
            out("  сверка с независимым обычным симулятором МТ: РАСХОЖДЕНИЕ ✗")
    elif info["status"] == "limit":
        out(f"  прервано по лимиту замен ({info['replacements']:,}); выполнено шагов МТ: "
            f"{info['tm_steps']}. Это НЕ доказательство зацикливания — просто лимит.".replace(",", " "))
    else:
        out("  непредусмотренное отсутствие правила: проверьте входные данные")


def rules_summary():
    return json.loads((ROOT / "rules_info.json").read_text(encoding="utf-8"))


def demo():
    print(ABOUT)
    info = rules_summary()
    print("=" * 72)
    print(f"ТАБЛИЦА ПРАВИЛ: {info['rules']} правил, алфавит {info['alphabet_size']} букв "
          f"({info['data_letters']} данных + {info['control_letters']} управляющих), "
          f"заключительных: {info['terminal_rules']}")
    print("Во всех примерах ниже используется ОДНА И ТА ЖЕ таблица — меняются только программа и вход.")
    print("=" * 72)

    failures = 0
    for n, (fname, word, comment, budget) in enumerate(DEMOS, 1):
        machine = load_machine(ROOT / "examples" / fname)
        print(f"\nПример {n}/{len(DEMOS)}: {comment}")
        print(describe_machine(machine))
        if budget >= 4_000_000:
            print("  (длинный пример — миллионы замен, подождите около десяти секунд...)", flush=True)
        info_run = run_machine(machine, word, budget=budget)
        print_result(machine, word, info_run)
        if info_run["status"] != "terminal" or info_run["reference_match"] is not True:
            failures += 1

    machine = load_machine(ROOT / "examples" / "loop_right.json")
    print("\nПример 7: машина, которая никогда не останавливается (идёт вправо вечно).")
    print(describe_machine(machine))
    info_run = run_machine(machine, "0110", budget=20_000)
    print_result(machine, "0110", info_run)

    machine = load_machine(ROOT / "examples" / "invert.json")
    print("\nПОД КАПОТОМ: первые 12 буквальных замен Маркова на инверсии «01011»")
    print("(⟨ИМЯ⟩ — одна управляющая буква-курсор; она бежит по слову обычными заменами)")
    run_machine(machine, "01011", micro=12, budget=12, check=False)

    print("\n" + "=" * 72)
    if failures:
        print(f"ИТОГ: {failures} пример(ов) не прошли проверку ✗")
    else:
        print("ИТОГ: все примеры выполнены правилами Маркова и совпали с обычным симулятором ✓")
    print("""
Что дальше:
  python3 app.py --menu                          интерактивное меню
  python3 app.py examples/task_1_11.json σ0011 --trace   задача практикума с трассой шагов
  python3 app.py --verify                        полная проверка (≈ 2–4 мин)
  python3 app.py --about                         только описание проекта
  python3 app.py --help                          все параметры
Свою машину задайте JSON-файлом (см. examples/ и `python3 app.py --format`).""")
    return 1 if failures else 0


def verify():
    print("Запускаю verify.py (≈ 2–4 минуты, без -O)...")
    return subprocess.call([sys.executable, str(ROOT / "verify.py")], cwd=ROOT)


def ask(prompt, default=""):
    try:
        value = input(prompt).strip()
    except EOFError:
        raise SystemExit(0)
    return value or default


def menu():
    examples = sorted((ROOT / "examples").glob("*.json"))
    while True:
        print("\n=== Универсальный алгоритм Маркова ===")
        print(" 1  демонстрация на готовых примерах")
        print(" 2  выбрать пример и ввести своё слово")
        print(" 3  загрузить свою машину из JSON-файла")
        print(" 4  что это за проект")
        print(" 5  полная проверка (≈ 1–2 мин)")
        print(" 6  формат файла машины")
        print(" 0  выход")
        choice = ask("Выбор: ")
        if choice == "1":
            demo()
        elif choice in ("2", "3"):
            if choice == "2":
                for i, p in enumerate(examples, 1):
                    print(f"  {i}. {p.stem}  — {load_machine(p).name}")
                idx = ask("Номер примера: ")
                if not idx.isdigit() or not 1 <= int(idx) <= len(examples):
                    print("Нет такого номера.")
                    continue
                path = examples[int(idx) - 1]
            else:
                path = Path(ask("Путь к JSON-файлу: "))
            try:
                machine = load_machine(path)
            except Exception as exc:
                print("Не удалось загрузить машину:", exc)
                continue
            word = ask("Входное слово в алфавите задач (Enter — пустое): ")
            try:
                print(describe_machine(machine))
                info = run_machine(machine, word, trace=ask("Показать трассу шагов? [y/N] ").lower() == "y",
                                   budget=int(ask("Лимит замен [1000000]: ", "1000000")))
                print_result(machine, word, info)
            except ValueError as exc:
                print("Ошибка входа:", exc)
        elif choice == "4":
            print(ABOUT)
        elif choice == "5":
            verify()
        elif choice == "6":
            print(FORMAT_HELP)
        elif choice == "0":
            return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Универсальный нормальный алгоритм Маркова: выполняет любую машину Тьюринга "
                    "одной фиксированной таблицей из 6962 правил. Без аргументов — описание и демо.")
    p.add_argument("machine", nargs="?", help="JSON-файл машины Тьюринга (см. examples/)")
    p.add_argument("word", nargs="?", default="", help="двоичное входное слово (по умолчанию пустое)")
    p.add_argument("--menu", action="store_true", help="интерактивное меню")
    p.add_argument("--demo", action="store_true", help="описание и демонстрация (по умолчанию)")
    p.add_argument("--about", action="store_true", help="показать описание проекта")
    p.add_argument("--verify", action="store_true", help="полная проверка verify.py")
    p.add_argument("--format", action="store_true", help="показать формат JSON-файла машины")
    p.add_argument("--trace", action="store_true", help="показать каждую конфигурацию МТ")
    p.add_argument("--micro", type=int, default=0, metavar="N", help="показать первые N замен Маркова")
    p.add_argument("--budget", type=int, default=1_000_000, help="лимит замен (не тест остановки)")
    p.add_argument("--plain", action="store_true", help="без фильтра неприменимых правил")
    args = p.parse_args(argv)

    if args.about:
        print(ABOUT)
        return 0
    if args.format:
        print(FORMAT_HELP)
        return 0
    if args.verify:
        return verify()
    if args.menu:
        return menu()
    if args.machine is None or args.demo:
        return demo()

    try:
        machine = load_machine(args.machine)
        print(describe_machine(machine))
        info = run_machine(machine, args.word, budget=args.budget, trace=args.trace,
                           micro=args.micro, plain=args.plain)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("Ошибка:", exc, file=sys.stderr)
        print(FORMAT_HELP, file=sys.stderr)
        return 2
    print_result(machine, args.word, info)
    return 0 if info["status"] != "no_rule" else 1


if __name__ == "__main__":
    sys.exit(main())
