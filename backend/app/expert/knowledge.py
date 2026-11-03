"""Снимок базы знаний (архитектура §4.2, §6.1): правила, справочники и анкета вместе.

Снимок неизменяем; при создании правила компилируются один раз, а статус компонентов
сверяется со справочниками снимка.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.expert.dsl.compiler import CompiledRuleSet, compile_rules
from app.expert.dsl.schema import Rule
from app.expert.frames import KnownSlotValues
from app.expert.questionnaire import Questionnaire
from app.expert.tables import KnowledgeTables


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    """Опубликованная (или собранная из файлов) версия базы знаний."""

    version: str
    rules: tuple[Rule, ...]
    tables: KnowledgeTables
    questionnaire: Questionnaire
    compiled: CompiledRuleSet

    @classmethod
    def build(
        cls,
        version: str,
        rules: Iterable[Rule],
        tables: KnowledgeTables,
        questionnaire: Questionnaire,
    ) -> "KnowledgeSnapshot":
        """Собирает снимок; `KnowledgeCompileError`, если правила не компилируются."""
        ordered = tuple(sorted(rules, key=lambda rule: rule.code))
        return cls(version, ordered, tables, questionnaire, compile_rules(ordered))

    @property
    def known_slot_values(self) -> KnownSlotValues:
        """Значения слотов, которые знает база знаний (для статуса `needs_kb`)."""
        return self.tables.known_slot_values()
