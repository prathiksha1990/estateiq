import argparse
import logging
import uuid

from .agent_graph import RealEstateAgentSystem


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ask the NJ real-estate intelligence agents")
    parser.add_argument("question", nargs="*")
    parser.add_argument("--database", default="data/processed/real_estate.db")
    parser.add_argument("--checkpoints", default="data/processed/conversations.db")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s %(message)s")
    system = RealEstateAgentSystem(args.database, args.checkpoints)
    thread_id = args.thread_id or str(uuid.uuid4())
    try:
        pending = " ".join(args.question).strip()
        while True:
            if not pending:
                pending = input("Question (blank to quit): ").strip()
                if not pending: break
            result = system.ask(pending, thread_id)
            interrupts = result.get("__interrupt__", ())
            while interrupts:
                prompt = interrupts[0].value.get("question", "Clarification required")
                result = system.resume(input(f"{prompt}\n> ").strip(), thread_id)
                interrupts = result.get("__interrupt__", ())
            print(result.get("final_answer", "No answer produced."))
            pending = ""
    finally:
        system.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

