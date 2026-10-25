"""A typical multi-turn chat client against the Gemini API, using the key and model in inputs/.env.

    python chat.py --demo    play a scripted conversation (a companion describing a collapse)
    python chat.py           chat interactively (type 'quit' to leave)

This is a mockup for trying the API: the assistant's safety rules mirror the Part 1 PRD
(de-escalate without false reassurance, one escort, no food or drink if stroke is suspected).
It is not medical advice.
"""
import argparse
import sys
import time

from google.genai import types

from src import config
from src.services.gemini_client import make_client

SYSTEM = """You help a bystander whose family member has suddenly fallen ill, on a remote island,
before the patient reaches the local health centre. Rules:
- Short, calm, plain English. At most 4 short sentences or steps per reply.
- Never guess how long someone will live and never promise they will be fine. Acknowledge fear honestly.
- If stroke is possible (face drooping, arm weakness, slurred speech): note the time symptoms started,
  give nothing to eat or drink, keep the person seated or lying on their side, and get them to the health centre now.
- Recommend that only ONE person escorts the patient; others stay and keep the household working.
- You are not a doctor. Do not diagnose. Say clearly when something needs a clinician."""

DEMO_TURNS = [
    "My father just collapsed. His face is drooping on one side and his words are slurred. What do I do?",
    "He says he's really thirsty. Can I give him some water?",
    "There are four of us here. How many should go with him to the clinic?",
    "Is he going to be okay?",
]


def send(chat, text: str) -> None:
    started = time.time()
    first_token_at = None
    usage = None
    print(f"\nYou: {text}\nAssistant: ", end="", flush=True)
    for chunk in chat.send_message_stream(text):
        if chunk.text:
            first_token_at = first_token_at or time.time()
            print(chunk.text, end="", flush=True)
        usage = chunk.usage_metadata or usage
    total = time.time() - started
    ttft = (first_token_at or time.time()) - started
    tokens = f"{usage.prompt_token_count} in / {usage.candidates_token_count} out" if usage else "n/a"
    print(f"\n  [{ttft:.1f}s to first words, {total:.1f}s total, tokens {tokens}]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="play the scripted conversation")
    args = parser.parse_args()

    if not config.GEMINI_API_KEY:
        print("No GEMINI_API_KEY in inputs/.env", file=sys.stderr)
        return 1

    client = make_client()  # keep this reference alive: the SDK closes the connection when it is collected
    chat = client.chats.create(
        model=config.GEMINI_CHAT_MODEL,
        config=types.GenerateContentConfig(system_instruction=SYSTEM),
    )
    print(f"Platform: {config.gemini_platform()} | model: {config.GEMINI_CHAT_MODEL}")

    if args.demo:
        for text in DEMO_TURNS:
            send(chat, text)
        return 0

    print("Chat started. Type 'quit' to leave.")
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("quit", "exit", ""):
            break
        send(chat, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
