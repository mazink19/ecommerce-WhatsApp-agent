"""UTF-8 terminal simulator for the WhatsApp sales assistant."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import TextIO

import agent


def configure_utf8() -> None:
    """Enable Arabic input and output on terminals that support reconfiguration."""
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def parse_command(command: str, phone: str) -> tuple[str, bool, str | None]:
    """Interpret a simulator slash command without sending it to Gemini.

    Args:
        command: The stripped line entered by the user.
        phone: The active simulated WhatsApp ID.

    Returns:
        The active phone, whether to keep the loop running, and an optional status message.
    """
    if command == "/quit":
        return phone, False, "Goodbye."
    if command == "/reset":
        agent.reset_session(phone)
        return phone, True, f"Reset the session for {phone}."
    if command.startswith("/phone "):
        next_phone = command.removeprefix("/phone ").strip()
        if next_phone:
            return next_phone, True, f"Switched to customer {next_phone}."
        return phone, True, "Usage: /phone <id>"
    return phone, True, "Commands: /phone <id>, /reset, /quit"


def print_tool_trace(phone: str, output: TextIO = sys.stdout) -> None:
    """Print the automatic function-call trace from the preceding turn.

    Args:
        phone: The simulated customer's WhatsApp ID.
        output: Stream used to render verbose diagnostics.

    Returns:
        None.
    """
    for call in agent.get_last_tool_calls(phone):
        arguments = json.dumps(call["arguments"], ensure_ascii=False)
        result = json.dumps(call["result"], ensure_ascii=False)
        print(f"[tool] {call['tool']}({arguments}) -> {result}", file=output)


def run_chat(
    phone: str,
    verbose: bool = False,
    input_fn: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> None:
    """Run the interactive terminal chat loop for one or more simulated customers.

    Args:
        phone: Initial simulated WhatsApp ID.
        verbose: Whether to display function calls and results.
        input_fn: Input callable, injected by tests when needed.
        output: Stream for replies and status messages.

    Returns:
        None.
    """
    active_phone = phone
    print(f"Simulator ready for {active_phone}. Type /quit to exit.", file=output)
    while True:
        try:
            text = input_fn(f"{active_phone}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.", file=output)
            return
        if not text:
            continue
        if text.startswith("/"):
            active_phone, keep_running, message = parse_command(text, active_phone)
            if message:
                print(message, file=output)
            if not keep_running:
                return
            continue
        reply = agent.handle_message(active_phone, text)
        if verbose:
            print_tool_trace(active_phone, output)
        print(f"Assistant: {reply}", file=output)


def main() -> None:
    """Parse command-line options and start the simulator."""
    parser = argparse.ArgumentParser(description="Simulate a WhatsApp store customer in the terminal.")
    parser.add_argument("--phone", default="201000000001", help="Initial simulated customer phone/WhatsApp ID")
    parser.add_argument("--verbose", action="store_true", help="Print tool calls and their backend results")
    args = parser.parse_args()
    configure_utf8()
    run_chat(args.phone, args.verbose)


if __name__ == "__main__":
    main()
