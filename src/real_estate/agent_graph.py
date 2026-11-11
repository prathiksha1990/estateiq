import json
import logging
import os
import re
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agent_models import AnalysisBundle, MarketReport, ResearchPlan, ToolResult, ValidationResult
from .agent_prompts import INTERPRETER_PROMPT, PLANNER_PROMPT, VALIDATOR_PROMPT
from .agent_state import AgentState
from .agent_tools import RealEstateToolkit
from .claim_validation import validate_numerical_claims

LOGGER = logging.getLogger(__name__)
MAX_VALIDATION_RETRIES = 2
MAX_TOOL_RETRIES = 2


def create_groq_model():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example and export the key.")
    return ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"), temperature=0, max_retries=2)


class RealEstateAgentSystem:
    def __init__(self, database: str | Path = "data/processed/real_estate.db",
                 checkpoint_path: str | Path | None = "data/processed/conversations.db",
                 planner_llm=None, interpreter_llm=None, validator_llm=None):
        self.database = Path(database)
        self.toolkit = RealEstateToolkit(self.database)
        base = planner_llm or create_groq_model()
        def structured(model, schema):
            if isinstance(model, ChatGroq):
                return model.with_structured_output(schema, method="json_schema", strict=False)
            return model.with_structured_output(schema)
        self.planner = structured(base, ResearchPlan)
        self.interpreter = structured(interpreter_llm or base, MarketReport)
        self.validator = structured(validator_llm or base, ValidationResult)
        self._checkpoint_connection = None
        if checkpoint_path is None:
            checkpointer = InMemorySaver()
        else:
            checkpoint_path = Path(checkpoint_path)
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
            checkpointer = SqliteSaver(self._checkpoint_connection)
        self.graph = self._build_graph().compile(checkpointer=checkpointer)

    @staticmethod
    def _invoke_structured(runnable, schema, messages):
        last_error = None
        for attempt in range(3):
            try:
                result = runnable.invoke(messages)
                return result if isinstance(result, schema) else schema.model_validate(result)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
        raise last_error

    @staticmethod
    def _compact_analysis(analysis: dict) -> dict:
        """Bound LLM context while retaining exact audit-relevant observations.

        Full tool results remain in graph state. For long time series, models see
        the earliest/latest and latest points on or before one/five years prior
        for each region; calculations themselves still happen in Python/SQL.
        """
        compact = {"question": analysis.get("question"), "errors": analysis.get("errors", []), "results": []}
        for result in analysis.get("results", []):
            item = {k: v for k, v in result.items() if k != "records"}
            records = result.get("records", [])
            if len(records) <= 40 or not all("date" in r and "region_name" in r for r in records):
                item["records"] = records
                compact["results"].append(item)
                continue
            selected = []
            names = sorted({r["region_name"] for r in records})
            for name in names:
                group = sorted((r for r in records if r["region_name"] == name), key=lambda r: r["date"])
                latest = group[-1]
                latest_date = date.fromisoformat(latest["date"][:10])
                picks = [group[0], latest]
                for years in (1, 5):
                    try:
                        target = latest_date.replace(year=latest_date.year - years)
                    except ValueError:
                        target = latest_date.replace(year=latest_date.year - years, day=28)
                    candidates = [r for r in group if date.fromisoformat(r["date"][:10]) <= target]
                    if candidates:
                        picks.append(candidates[-1])
                seen = set()
                for record in sorted(picks, key=lambda r: r["date"]):
                    key = (record.get("region_id"), record["date"], record.get("metric_name"))
                    if key not in seen:
                        selected.append(record); seen.add(key)
            item["records"] = selected
            item["record_selection"] = "earliest, latest, and latest observations on/before 1- and 5-year anniversaries"
            item["full_record_count"] = len(records)
            compact["results"].append(item)
        return compact

    def _plan(self, state: AgentState) -> dict:
        prior = {"towns": state.get("context_towns", []), "metrics": state.get("context_metrics", []),
                 "geography": state.get("context_geography")}
        prompt = {"question": state["question"], "previous_context": prior}
        try:
            question = state["question"]
            lowered = question.casefold()
            if self._is_property_valuation(lowered):
                towns = self._locations_in_question(question, "city")
                plan = ResearchPlan(interpreted_question=question, towns=towns, metrics=[],
                                    geography="city", tools=[])
                return {"plan": plan.model_dump(), "retry_count": 0, "execution_retry_count": 0,
                        "error": None, "terminal_answer":
                        "EstateIQ cannot determine whether an individual property is undervalued from town-level Zillow Research data. Property-level valuation requires property-specific characteristics and comparable sales that are not available in this database.",
                        "analysis": {}, "report": {}, "validation": {}, "final_answer": "",
                        "context_towns": towns}
            if self._explicit_unsupported_metric(question):
                towns = self._locations_in_question(question, "city")
                plan = ResearchPlan(interpreted_question=question, towns=towns, metrics=[],
                                    geography="city", tools=[])
                return {"plan": plan.model_dump(), "retry_count": 0, "execution_retry_count": 0,
                        "error": None, "terminal_answer": self._unavailable_answer(question),
                        "analysis": {}, "report": {}, "validation": {}, "final_answer": "",
                        "context_towns": towns}
            unsupported_location = self._explicit_unsupported_location(question)
            if unsupported_location:
                plan = ResearchPlan(interpreted_question=question, towns=[unsupported_location],
                                    metrics=[], geography="city", tools=[])
                return {"plan": plan.model_dump(), "retry_count": 0, "execution_retry_count": 0,
                        "error": None, "terminal_answer": self._unavailable_answer(question),
                        "analysis": {}, "report": {}, "validation": {}, "final_answer": "",
                        "context_towns": [unsupported_location]}
            if self._is_broad_statewide_question(question):
                answer = interrupt({"type": "clarification", "question":
                    "Which New Jersey city or metro area and which market metrics should I analyze?"})
                prompt["clarification_response"] = str(answer)
            plan = self._invoke_structured(self.planner, ResearchPlan, [
                SystemMessage(content=PLANNER_PROMPT), HumanMessage(content=json.dumps(prompt))])
            inferred = self._locations_in_question(question, plan.geography)
            if not plan.towns and inferred:
                plan = plan.model_copy(update={"towns": inferred})
            clarification = (plan.clarification_question or "").casefold()
            if (plan.requires_clarification and "time period" in clarification and
                    "latest" in lowered and "appreciation" in lowered):
                plan = plan.model_copy(update={"requires_clarification": False,
                                               "clarification_question": None})
            if self._is_statewide_ambiguous(lowered, plan):
                plan = plan.model_copy(update={"requires_clarification": True,
                    "clarification_question": "Which New Jersey city or metro area and which market metrics should I analyze?"})
            if plan.requires_clarification and self._clarification_is_terminal(plan):
                unsupported = self._unsupported_name(plan.clarification_question or "")
                towns = plan.towns or ([unsupported] if unsupported else inferred)
                plan = plan.model_copy(update={"towns": towns, "requires_clarification": False,
                                               "clarification_question": None, "tools": []})
                return {"plan": plan.model_dump(), "retry_count": 0, "execution_retry_count": 0,
                        "error": None, "terminal_answer": self._unavailable_answer(question),
                        "analysis": {}, "report": {}, "validation": {}, "final_answer": "",
                        "context_towns": towns}
            if plan.requires_clarification:
                answer = interrupt({"type": "clarification", "question": plan.clarification_question or
                                    "Please clarify the intended New Jersey location, metric, or time period."})
                prompt["clarification_response"] = str(answer)
                plan = self._invoke_structured(self.planner, ResearchPlan, [
                    SystemMessage(content=PLANNER_PROMPT), HumanMessage(content=json.dumps(prompt))])
            return {"plan": plan.model_dump(), "retry_count": 0, "execution_retry_count": 0, "error": None,
                    "analysis": {}, "report": {}, "validation": {}, "final_answer": ""}
        except GraphInterrupt:
            raise
        except Exception as exc:
            LOGGER.exception("Planning failed")
            return {"error": f"Planning failed: {exc}"}

    @staticmethod
    def _is_property_valuation(question: str) -> bool:
        property_scope = (bool(re.search(r"\b\d{1,6}\s+[a-z]", question)) or
                          ("specific" in question and any(term in question for term in ("house", "home", "property"))))
        return "undervalued" in question and property_scope

    @staticmethod
    def _explicit_unsupported_metric(question: str) -> bool:
        normalized = question.casefold().replace("‑", "-").replace("–", "-")
        return any(term in normalized for term in ("price-cut share", "price cut share"))

    def _explicit_unsupported_location(self, question: str) -> str | None:
        match = re.search(r"\bin\s+([A-Za-z][A-Za-z .'-]+?)\s+(?:New Jersey|NJ)\b", question, re.I)
        if not match:
            return None
        candidate = match.group(1).strip()
        candidate = re.sub(r"^the\s+", "", candidate, flags=re.I)
        geography = "msa" if "metro" in question.casefold() else "city"
        supported = self.toolkit.available_locations(geography, None)["records"]
        aliases = {record["region_name"].split(",")[0].casefold() for record in supported}
        return candidate if candidate.casefold() not in aliases else None

    @staticmethod
    def _is_statewide_ambiguous(question: str, plan: ResearchPlan) -> bool:
        return "new jersey" in question and not plan.towns and len(plan.metrics) > 1

    def _is_broad_statewide_question(self, question: str) -> bool:
        lowered = question.casefold()
        if "new jersey" not in lowered or "market" not in lowered:
            return False
        return not (self._locations_in_question(question, "city") or
                    self._locations_in_question(question, "msa"))

    @staticmethod
    def _clarification_is_terminal(plan: ResearchPlan) -> bool:
        text = (plan.clarification_question or "").casefold()
        return any(term in text for term in ("not currently available", "not available", "valid town", "valid city"))

    @staticmethod
    def _unsupported_name(text: str) -> str | None:
        match = re.search(r"['\"]([^'\"]+)['\"]", text)
        return match.group(1) if match else None

    @staticmethod
    def _unavailable_answer(question: str) -> str:
        if "price-cut" in question.casefold() or "price cut" in question.casefold():
            return "Price-cut share is not available in the loaded Zillow Research datasets. EstateIQ will not substitute another metric."
        return "The requested New Jersey location is not available in the loaded Zillow Research data. EstateIQ will not substitute another location."

    def _locations_in_question(self, question: str, geography: str | None) -> list[str]:
        if not geography:
            return []
        lowered = question.casefold()
        records = self.toolkit.available_locations(geography, None)["records"]
        matches = []
        for record in records:
            name = record["region_name"]
            alias = name.split(",")[0].casefold()
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                matches.append(name)
        return sorted(set(matches), key=lambda value: lowered.find(value.split(",")[0].casefold()))

    def _resolve_locations(self, plan: ResearchPlan) -> ResearchPlan:
        if not plan.towns or not plan.geography:
            return plan
        locations = self.toolkit.available_locations(plan.geography, None)["records"]
        resolved = []
        for requested in plan.towns:
            id_match = [record for record in locations if str(record["region_id"]).casefold() == requested.casefold()]
            if len(id_match) == 1:
                resolved.append(id_match[0]["region_name"]); continue
            exact = [record for record in locations if record["region_name"].casefold() == requested.casefold()]
            if len(exact) == 1:
                resolved.append(exact[0]["region_name"]); continue
            if len(exact) > 1:
                options = [f"{record['region_name']} [Zillow region {record['region_id']}]" for record in exact]
                choice = interrupt({"type": "clarification", "question":
                    f"'{requested}' matches multiple {plan.geography} regions: {options}. Which Zillow region ID?"})
                chosen = [record for record in exact if str(record["region_id"]) == str(choice)]
                resolved.append(str(chosen[0]["region_id"]) if chosen else str(choice)); continue
            alias = [record for record in locations
                     if record["region_name"].split(",")[0].casefold() == requested.casefold()]
            if len(alias) == 1:
                resolved.append(alias[0]["region_name"]); continue
            if len(alias) > 1:
                options = [f"{record['region_name']} [Zillow region {record['region_id']}]" for record in alias]
                choice = interrupt({"type": "clarification", "question":
                    f"'{requested}' matches multiple {plan.geography} regions: {options}. Which Zillow region ID?"})
                chosen = [record for record in alias if str(record["region_id"]) == str(choice)]
                resolved.append(str(chosen[0]["region_id"]) if chosen else str(choice))
            else:
                resolved.append(requested)
        return plan.model_copy(update={"towns": resolved})

    def _execute(self, state: AgentState) -> dict:
        try:
            plan = self._resolve_locations(ResearchPlan.model_validate(state["plan"]))
            results: list[ToolResult] = []
            requested = list(dict.fromkeys(plan.tools))
            if not requested:
                requested.append("compare_markets" if len(plan.towns) > 1 else "get_latest_market_metric")
            execution_retries = 0
            def call(operation, tool_name: str, metric: str | None = None):
                nonlocal execution_retries
                for attempt in range(MAX_TOOL_RETRIES + 1):
                    try:
                        return operation()
                    except sqlite3.Error as exc:
                        transient = self._is_transient_database_error(exc)
                        if not transient or attempt >= MAX_TOOL_RETRIES:
                            return ToolResult(tool=tool_name, status="error", metric=metric,
                                geography=plan.geography,
                                message=f"Data operation failed after {attempt + 1} attempt(s): {exc}").model_dump()
                        execution_retries += 1
                        time.sleep(0.05 * (2 ** attempt))
            for tool_name in requested:
                if tool_name == "list_available_metrics": raw = call(self.toolkit.available_metrics, tool_name)
                elif tool_name == "list_available_locations": raw = call(
                    lambda: self.toolkit.available_locations(plan.geography, plan.metrics[0] if plan.metrics else None), tool_name)
                elif tool_name == "get_home_value_trend": raw = call(
                    lambda: self.toolkit.home_value_trend(plan.towns[0]), tool_name, "zhvi") if plan.towns else ToolResult(tool=tool_name, status="unavailable", message="No town supplied.").model_dump()
                elif tool_name == "calculate_appreciation":
                    if plan.towns:
                        pieces = [call(lambda town=town: self.toolkit.appreciation(town), tool_name, "zhvi")
                                  for town in plan.towns]
                        results.extend(ToolResult.model_validate(x) for x in pieces); continue
                    raw = ToolResult(tool=tool_name, status="unavailable", message="No town supplied.").model_dump()
                elif tool_name == "compare_markets":
                    if plan.metrics:
                        for metric in plan.metrics:
                            raw = call(lambda metric=metric: self.toolkit.compare(metric, plan.towns, plan.geography or "city", plan.start_date, plan.end_date), tool_name, metric)
                            results.append(ToolResult.model_validate(raw))
                        continue
                    raw = ToolResult(tool=tool_name, status="unavailable", message="No metric supplied.").model_dump()
                elif tool_name == "get_latest_market_metric":
                    metrics = plan.metrics or ["zhvi"]
                    for metric in metrics:
                        if plan.towns:
                            for town in plan.towns:
                                raw = call(lambda metric=metric, town=town: self.toolkit.latest(metric, town, plan.geography), tool_name, metric)
                                results.append(ToolResult.model_validate(raw))
                        else:
                            raw = call(lambda metric=metric: self.toolkit.latest(metric, None, plan.geography), tool_name, metric)
                            results.append(ToolResult.model_validate(raw))
                    continue
                else:
                    raw = ToolResult(tool=tool_name, status="error", message="Tool is not approved.").model_dump()
                results.append(ToolResult.model_validate(raw))
            bundle = AnalysisBundle(question=state["question"], results=results,
                                    errors=[r.message for r in results if r.status != "ok" and r.message])
            terminal = None
            if results and all(result.status == "error" for result in results):
                terminal = "EstateIQ could not retrieve the requested data after bounded retries. " + " ".join(bundle.errors)
            return {"analysis": bundle.model_dump(), "plan": plan.model_dump(), "error": None,
                    "terminal_answer": terminal,
                    "execution_retry_count": execution_retries,
                    "context_towns": plan.towns or state.get("context_towns", []),
                    "context_metrics": plan.metrics or state.get("context_metrics", []),
                    "context_geography": plan.geography or state.get("context_geography")}
        except GraphInterrupt:
            raise
        except Exception as exc:
            LOGGER.exception("Tool execution failed")
            return {"error": f"Data tool execution failed: {exc}"}

    @staticmethod
    def _is_transient_database_error(exc: sqlite3.Error) -> bool:
        if not isinstance(exc, sqlite3.OperationalError):
            return False
        text = str(exc).casefold()
        return any(term in text for term in ("locked", "busy", "temporary", "transient", "interrupted", "i/o"))

    def _interpret(self, state: AgentState) -> dict:
        try:
            payload = {"question": state["question"], "research_plan": state["plan"],
                       "tool_results": self._compact_analysis(state["analysis"]),
                       "prior_validation": state.get("validation", {})}
            report = self._invoke_structured(self.interpreter, MarketReport, [
                SystemMessage(content=INTERPRETER_PROMPT), HumanMessage(content=json.dumps(payload))])
            return {"report": report.model_dump(), "error": None}
        except Exception as exc:
            LOGGER.exception("Interpretation failed")
            return {"error": f"Market interpretation failed: {exc}"}

    def _validate(self, state: AgentState) -> dict:
        try:
            report = MarketReport.model_validate(state["report"])
            deterministic = validate_numerical_claims(report.answer, state["analysis"])
            if not deterministic.valid:
                count = state.get("retry_count", 0) + 1
                errors = [f"Unverified numerical claim {item['claim']}: {', '.join(item['reasons'])}"
                          for item in deterministic.unverified_claims]
                return {"deterministic_validation": deterministic.__dict__,
                        "validation": ValidationResult(valid=False, numerical_claims_verified=False,
                            geography_verified=False, units_and_dates_verified=False,
                            answers_question=True, errors=errors,
                            correction_instructions="Use only numerical claims that bind to the supplied metric, location, geography, date, unit, value, and direction.").model_dump(),
                        "retry_count": count, "error": None}
            payload = {"question": state["question"],
                       "tool_results": self._compact_analysis(state["analysis"]), "draft": state["report"]}
            result = self._invoke_structured(self.validator, ValidationResult, [
                SystemMessage(content=VALIDATOR_PROMPT), HumanMessage(content=json.dumps(payload))])
            return {"deterministic_validation": deterministic.__dict__, "validation": result.model_dump(),
                    "retry_count": state.get("retry_count", 0) + (0 if result.valid else 1), "error": None}
        except Exception as exc:
            LOGGER.exception("Validation failed")
            count = state.get("retry_count", 0) + 1
            return {"validation": ValidationResult(valid=False, numerical_claims_verified=False,
                    geography_verified=False, units_and_dates_verified=False, answers_question=False,
                    errors=[str(exc)], correction_instructions="Regenerate conservatively from tool results.").model_dump(),
                    "retry_count": count, "error": None}

    @staticmethod
    def _finish(state: AgentState) -> dict:
        if state.get("terminal_answer"):
            answer = state["terminal_answer"]
        elif state.get("error"):
            answer = state["error"]
        else:
            report = MarketReport.model_validate(state["report"])
            answer = report.answer
            if report.limitations:
                answer += "\n\nLimitations: " + " ".join(report.limitations)
            validation = ValidationResult.model_validate(state["validation"])
            if not validation.valid:
                answer = "Validation could not fully approve this answer after two corrections.\n\n" + answer
        return {"final_answer": answer}

    @staticmethod
    def _route_error(state: AgentState) -> str:
        return "finish" if state.get("error") or state.get("terminal_answer") else "continue"

    @staticmethod
    def _route_validation(state: AgentState) -> str:
        validation = ValidationResult.model_validate(state["validation"])
        return "finish" if validation.valid or state.get("retry_count", 0) >= MAX_VALIDATION_RETRIES else "retry"

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("planning", self._plan)
        graph.add_node("tool_execution", self._execute)
        graph.add_node("market_interpretation", self._interpret)
        graph.add_node("answer_validation", self._validate)
        graph.add_node("finish", self._finish)
        graph.add_edge(START, "planning")
        graph.add_conditional_edges("planning", self._route_error, {"continue": "tool_execution", "finish": "finish"})
        graph.add_conditional_edges("tool_execution", self._route_error, {"continue": "market_interpretation", "finish": "finish"})
        graph.add_conditional_edges("market_interpretation", self._route_error, {"continue": "answer_validation", "finish": "finish"})
        graph.add_conditional_edges("answer_validation", self._route_validation,
                                    {"retry": "market_interpretation", "finish": "finish"})
        graph.add_edge("finish", END)
        return graph

    def ask(self, question: str, thread_id: str = "default") -> dict[str, Any]:
        return self.graph.invoke({"question": question}, {"configurable": {"thread_id": thread_id}})

    def resume(self, response: str, thread_id: str = "default") -> dict[str, Any]:
        from langgraph.types import Command
        return self.graph.invoke(Command(resume=response), {"configurable": {"thread_id": thread_id}})

    def close(self):
        if self._checkpoint_connection is not None:
            self._checkpoint_connection.close()

