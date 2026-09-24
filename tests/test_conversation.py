from datapilot.agent import AgentResult, HistoryTurn
from datapilot.conversation import Conversation


class FakeAgent:
    """Records the history it was given and answers with a numbered reply."""

    def __init__(self) -> None:
        self.histories: list[list[HistoryTurn]] = []

    def run(self, question: str, history: list[HistoryTurn] | None = None) -> AgentResult:
        self.histories.append(list(history or []))
        number = len(self.histories)
        return AgentResult(question=question, answer=f"answer {number}", steps=[],
                           final_sql=f"SELECT {number}")


def test_follow_up_receives_previous_turns_with_sql() -> None:
    agent = FakeAgent()
    conversation = Conversation(agent)

    conversation.ask("Show participation in 2026.")
    conversation.ask("What about Coimbatore?")

    assert agent.histories[0] == []
    assert agent.histories[1] == [
        HistoryTurn(question="Show participation in 2026.", answer="answer 1", sql="SELECT 1")
    ]


def test_only_recent_turns_are_kept() -> None:
    agent = FakeAgent()
    conversation = Conversation(agent, max_turns_kept=2)

    for number in range(4):
        conversation.ask(f"question {number}")

    assert [turn.question for turn in agent.histories[-1]] == ["question 1", "question 2"]


def test_reset_forgets_everything() -> None:
    agent = FakeAgent()
    conversation = Conversation(agent)
    conversation.ask("first")
    conversation.reset()
    conversation.ask("second")

    assert agent.histories[-1] == []
    assert conversation.last_result.question == "second"
