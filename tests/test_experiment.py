"""Runner không để gold lọt vào agent (src/experiment.py)."""
import json
import unittest

from src import experiment as E
from src import lab_config as C


class AgentInputsTest(unittest.TestCase):
    def test_only_question_and_filter_reach_the_agent(self):
        q = {"id": "q06", "split": "dev", "question": "Theo Chương II…?", "answerable": True,
             "expected_answer": "60 ngày", "gold": [{"source_id": "nd13", "page": 21, "evidence": "60 ngày"}],
             "filter": {"chapter": "Chương II"}, "metadata": {"day6_type": "x"}}
        inputs = E.agent_inputs(q)
        self.assertEqual(inputs, {"question": "Theo Chương II…?", "filters": {"chapter": "Chương II"}})
        self.assertNotIn("60 ngày", json.dumps(inputs, ensure_ascii=False))

    def test_unanswerable_reason_never_reaches_the_agent(self):
        for q in json.loads(C.QUESTIONS.read_text("utf-8")):
            inputs = json.dumps(E.agent_inputs(q), ensure_ascii=False)
            for secret in (q.get("expected_answer"), q.get("absence_reason")):
                if secret:
                    self.assertNotIn(secret, inputs, q["id"])


if __name__ == "__main__":
    unittest.main()
