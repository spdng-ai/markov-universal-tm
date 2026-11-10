"""Общий буквальный интерпретатор нормальных алгоритмов Маркова.

Про машины Тьюринга здесь ничего не известно: только список правил и слово.
"""
from dataclasses import dataclass
from functools import lru_cache
import json


@dataclass(frozen=True)
class Rule:
    lhs: str
    rhs: str
    terminal: bool = False
    group: str = ""


@dataclass(frozen=True)
class Replacement:
    word: str
    rule_index: int                 # с нуля
    position: int
    terminal: bool


@dataclass(frozen=True)
class RunResult:
    word: str
    replacements: int
    status: str                     # terminal / no_rule / limit


def load_rules(path):
    return tuple(Rule(**item) for item in json.loads(path.read_text(encoding="utf-8")))


class Markov:
    def __init__(self, rules, *, alphabet_filter=True):
        self.rules = tuple(rules)
        self.alphabet_filter = alphabet_filter
        # Индекс по первым двум буквам левой части: если какой-то из них нет во
        # всём слове, вхождение заведомо невозможно. Порядок правил и поиск
        # вхождения фильтр не меняет; проверяется обычным str.find как раньше.
        buckets = {}
        self._empty_lhs = tuple(i for i, r in enumerate(self.rules) if not r.lhs)
        for i, rule in enumerate(self.rules):
            if len(rule.lhs) >= 2:
                buckets.setdefault(rule.lhs[0], {}).setdefault(rule.lhs[1], []).append(i)
            elif rule.lhs:
                buckets.setdefault(rule.lhs[0], {}).setdefault(None, []).append(i)
        self._by_first = {c: {d: tuple(ix) for d, ix in seconds.items()}
                          for c, seconds in buckets.items()}
        self._candidates = lru_cache(maxsize=2048)(self._filter)

    def _filter(self, present):
        indices = set(self._empty_lhs)
        for letter, seconds in self._by_first.items():
            if letter not in present:
                continue
            for second, ix in seconds.items():
                if second is None or second in present:
                    indices.update(ix)
        return tuple(sorted(indices))

    def step(self, word):
        indices = (self._candidates(frozenset(word)) if self.alphabet_filter
                   else range(len(self.rules)))
        for i in indices:            # приоритет — исходный порядок правил
            rule = self.rules[i]
            pos = word.find(rule.lhs)  # самое левое вхождение; для "" будет 0
            if pos != -1:
                changed = word[:pos] + rule.rhs + word[pos + len(rule.lhs):]
                return Replacement(changed, i, pos, rule.terminal)
        return None

    def run(self, word, max_replacements=1000000, observer=None):
        if max_replacements < 0:
            raise ValueError("max_replacements должен быть неотрицательным")
        for count in range(1, max_replacements + 1):
            applied = self.step(word)
            if applied is None:
                return RunResult(word, count - 1, "no_rule")
            word = applied.word
            if observer is not None:
                observer(count, applied)  # наблюдатель только смотрит; его ответ не используется
            if applied.terminal:
                return RunResult(word, count, "terminal")
        # limit ничего не говорит об остановке в принципе — просто кончился бюджет
        return RunResult(word, max_replacements, "limit")
