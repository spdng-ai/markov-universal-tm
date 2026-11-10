"""Запуск машины ТОЛЬКО правилами Маркова; reference.py тут не импортируется."""
from pathlib import Path
import argparse
import json
from engine import Markov, load_rules
from codec import controls, encode, decode_stable, load_machine, readable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("machine", help="JSON-файл с машиной Тьюринга")
    parser.add_argument("word", nargs="?", default="",
                        help="входное слово в алфавите задач (по умолчанию пустое)")
    parser.add_argument("--budget", type=int, default=1000000,
                        help="максимум замен; это не тест на остановку")
    parser.add_argument("--trace", action="store_true", help="показывать каждую стабильную конфигурацию")
    parser.add_argument("--micro", type=int, default=0, help="показать первые N замен Маркова")
    parser.add_argument("--plain", action="store_true", help="без фильтра неприменимых правил")
    parser.add_argument("--encode-only", action="store_true", help="вывести только кодированный вход")
    args = parser.parse_args()
    machine = load_machine(args.machine)
    word = encode(machine, args.word)
    if args.encode_only:
        print(word)
        return
    root = Path(__file__).parent
    rules = load_rules(root / "rules.json")
    names = controls()
    ready = names["READY"]
    simulated = 0
    if args.trace:
        print("МТ 0 / НАМ 0:", decode_stable(word, ready).human())

    def observer(count, applied):
        nonlocal simulated
        if count <= args.micro:
            r = rules[applied.rule_index]
            print(f"НАМ {count}, правило {applied.rule_index + 1}, позиция {applied.position}:",
                  readable(r.lhs, names), "→·" if r.terminal else "→", readable(r.rhs, names))
            print("   ", readable(applied.word, names))
        if applied.word.startswith(ready + "^"):
            simulated += 1
            if args.trace:
                print(f"МТ {simulated} / НАМ {count}:", decode_stable(applied.word, ready).human())

    result = Markov(rules, alphabet_filter=not args.plain).run(word, args.budget, observer)
    print(f"статус={result.status}; шагов МТ={simulated}; замен НАМ={result.replacements}")
    if result.status == "terminal":
        snap = decode_stable(result.word, ready)
        print("Итог:", snap.human())
        print("Лента без внешних пустых ячеек:", repr(snap.window.strip("_")))
        print("Слово-результат (JSON):", json.dumps(result.word, ensure_ascii=True))
    elif result.status == "limit":
        print("Проверка прервана по лимиту; это НЕ доказательство зацикливания.")
    else:
        print("Непредусмотренное отсутствие правила: проверьте вход или конструкцию.")


if __name__ == "__main__":
    main()
