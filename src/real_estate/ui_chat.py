"""Framework-independent conversation state transitions for the UI."""

from collections.abc import MutableMapping
from typing import Any


def process_message(agent, state: MutableMapping[str, Any], text: str) -> dict[str, Any]:
    """Submit or resume one message and update UI conversation state.

    This deliberately contains no Streamlit calls so rerun behavior, errors, and
    human-in-the-loop transitions can be tested without a browser.
    """
    state.setdefault("messages", [])
    state.setdefault("pending_clarification", False)
    state["messages"].append({"role": "user", "content": text})
    try:
        if state["pending_clarification"]:
            result = agent.resume(text, state["thread_id"])
            state["pending_clarification"] = False
        else:
            result = agent.ask(text, state["thread_id"])
        interrupts = result.get("__interrupt__", ())
        if interrupts:
            value = interrupts[0].value
            prompt = value.get("question", "Please clarify your request.") if isinstance(value, dict) else str(value)
            state["pending_clarification"] = True
            state["messages"].append({"role": "assistant", "content": prompt, "clarification": True})
            return {"status": "clarification", "result": result, "message": prompt}
        answer = result.get("final_answer", "The workflow did not produce an answer.")
        state["last_agent_state"] = result
        state["messages"].append({"role": "assistant", "content": answer})
        return {"status": "error" if result.get("error") else "complete", "result": result, "message": answer}
    except Exception as exc:
        message = f"The research workflow could not complete: {exc}"
        state["messages"].append({"role": "assistant", "content": message, "error": True})
        return {"status": "error", "result": None, "message": message}

