"""Conversation memory: earlier turns are sent back to the model on every question.

Gemini is stateless, so "What about Coimbatore?" only makes sense if we resend
what came before. We keep each turn as question + answer + the SQL that produced
it: the SQL carries the filters (year, city) that follow-up questions build on.

Only the last MAX_TURNS_KEPT turns are sent. Older turns are dropped rather than
summarised: simpler and predictable, at the cost of forgetting long-ago context.

Any answerer with run(question, history) works: the agent (thorough mode) or
FastAnswerer (fast mode). The mode can change from one question to the next.
"""
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
