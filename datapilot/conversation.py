"""Conversation memory. The last few turns (question, answer and SQL) are sent
with each new question so follow-ups like "What about Coimbatore?" work."""
from typing import Protocol

from datapilot.agent import AgentResult, HistoryTurn

MAX_TURNS_KEPT = 6


class Answerer(Protocol):
    def run(self, question: str, history: list[HistoryTurn] | None = None) -> AgentResult: ...


class Conversation:
    def __init__(self, agent: Answerer, max_turns_kept: int = MAX_TURNS_KEPT) -> None:
        self.agent = agent
        self.max_turns_kept = max_turns_kept
        self.turns: list[HistoryTurn] = []
        self.last_result: AgentResult | None = None

    def ask(self, question: str, answerer: Answerer | None = None) -> AgentResult:
        history = self.turns[-self.max_turns_kept:]
        result = (answerer or self.agent).run(question, history=history)

        self.turns.append(HistoryTurn(question=question, answer=result.answer, sql=result.final_sql))
        self.last_result = result
        return result

    def reset(self) -> None:
        self.turns.clear()
        self.last_result = None
