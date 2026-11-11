import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from .models import JudgeResult
from .models import EvaluationCase

JUDGE_PROMPT = """You are evaluating an EstateIQ answer. Use only the supplied
question, database evidence, and answer. Do not add external real-estate facts.
Score each dimension from 1 to 5:
- relevance: directly answers the request and handles unavailable scope
- groundedness: claims are supported by supplied evidence
- clarity: dates, units, metrics, and geography are understandable
- overstatement: 5 means conclusions are appropriately limited; 1 means severe overclaiming
The expected behavior and required coverage are part of the benchmark. An answer
that is accurate only because a requested metric or location was omitted is not
complete. Set passed=true only when every score is at least 3 and the answer
meets the expected behavior and required coverage. Give a concise rationale.
"""


class LLMJudge:
    def __init__(self, model: ChatGroq, max_attempts: int = 3):
        self.runnable = model.with_structured_output(JudgeResult, method="json_schema", strict=False)
        self.max_attempts = max_attempts

    def evaluate(self, case: EvaluationCase, evidence: dict, answer: str) -> JudgeResult:
        payload = {"question": case.question, "expected_behavior": case.expected_behavior,
                   "required_metrics": case.expected_metrics, "required_locations": case.expected_locations,
                   "retrieved_evidence": evidence, "final_response": answer}
        last_error = None
        for attempt in range(self.max_attempts):
            try:
                result = self.runnable.invoke([
                    SystemMessage(content=JUDGE_PROMPT), HumanMessage(content=json.dumps(payload, default=str))])
                return result if isinstance(result, JudgeResult) else JudgeResult.model_validate(result)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM judge failed after {self.max_attempts} attempts: {last_error}")

