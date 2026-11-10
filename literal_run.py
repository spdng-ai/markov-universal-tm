"""Отдельный CLI общего интерпретатора замен: без разбора машины и без симуляции."""
from pathlib import Path
import argparse
import json
import sys
from engine import Markov, load_rules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rules", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("--budget", type=int, default=1000000)
    parser.add_argument("--plain", action="store_true")
    args = parser.parse_args()
    word = args.input.read_text(encoding="utf-8").removesuffix("\n")
    result = Markov(load_rules(args.rules), alphabet_filter=not args.plain).run(word, args.budget)
    print(result.word)
    print(json.dumps({"status": result.status, "replacements": result.replacements}), file=sys.stderr)


if __name__ == "__main__":
    main()
