"""Collab CLI: ChatGPT propose, Claude critique, l'utilisateur arbitre."""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from collab.prompts import PROPOSER_SYSTEM, REVIEWER_SYSTEM

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "history"
BACKTEST_QUEUE = ROOT.parent / "trading" / "backtest_queue.json"


def read_multiline(prompt: str) -> str:
    print(prompt)
    print("(Colle la réponse, puis une ligne contenant uniquement 'EOF' pour terminer)")
    lines = []
    for line in sys.stdin:
        if line.strip() == "EOF":
            break
        lines.append(line)
    return "".join(lines).strip()


def call_openai_api(messages, model: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content


def call_anthropic_api(system: str, messages, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


def ask_proposer_manual(prompt_text: str, round_num: int) -> str:
    banner = f"\n{'=' * 70}\n>>> ROUND {round_num} — PROPOSER (ChatGPT)\n{'=' * 70}"
    print(banner)
    print("\nCOPIE CE BLOC DANS CHATGPT (avec le system prompt en première fois):\n")
    print("-" * 70)
    if round_num == 1:
        print("[SYSTEM PROMPT — à coller au tout début de la conversation ChatGPT]")
        print(PROPOSER_SYSTEM)
        print("\n[USER MESSAGE]")
    print(prompt_text)
    print("-" * 70)
    return read_multiline("\nColle la réponse de ChatGPT ci-dessous:")


def ask_reviewer_manual(proposal: str, round_num: int) -> str:
    banner = f"\n{'=' * 70}\n>>> ROUND {round_num} — REVIEWER (Claude)\n{'=' * 70}"
    print(banner)
    print("\nCOPIE CE BLOC DANS CLAUDE (web/app) avec le system prompt en première fois:\n")
    print("-" * 70)
    if round_num == 1:
        print("[SYSTEM PROMPT]")
        print(REVIEWER_SYSTEM)
        print("\n[USER MESSAGE]")
    print("Voici les setups proposés à critiquer:\n")
    print(proposal)
    print("-" * 70)
    return read_multiline("\nColle la réponse de Claude ci-dessous:")


def run_api_mode(topic: str, rounds: int, gpt_model: str, claude_model: str):
    gpt_history = [{"role": "system", "content": PROPOSER_SYSTEM}]
    claude_history = []

    proposal = ""
    critique = ""
    transcript = []

    user_msg = topic
    for r in range(1, rounds + 1):
        gpt_history.append({"role": "user", "content": user_msg})
        print(f"\n>>> Round {r} — ChatGPT propose...")
        proposal = call_openai_api(gpt_history, gpt_model)
        gpt_history.append({"role": "assistant", "content": proposal})
        transcript.append((f"Round {r} — Proposer (ChatGPT)", proposal))
        print(proposal)

        claude_history.append({
            "role": "user",
            "content": f"Sujet initial: {topic}\n\nVoici les setups proposés:\n\n{proposal}",
        })
        print(f"\n>>> Round {r} — Claude critique...")
        critique = call_anthropic_api(REVIEWER_SYSTEM, claude_history, claude_model)
        claude_history.append({"role": "assistant", "content": critique})
        transcript.append((f"Round {r} — Reviewer (Claude)", critique))
        print(critique)

        user_msg = f"Voici la critique de ton reviewer:\n\n{critique}\n\nPropose une version révisée des setups [REFINE], et garde tels quels les [BACKTEST_NOW]."

    return transcript, critique


def run_manual_mode(topic: str, rounds: int):
    transcript = []
    user_msg = topic
    critique = ""

    for r in range(1, rounds + 1):
        proposal = ask_proposer_manual(user_msg, r)
        transcript.append((f"Round {r} — Proposer (ChatGPT)", proposal))

        critique_input = (
            f"Sujet initial: {topic}\n\n"
            f"Voici les setups proposés:\n\n{proposal}"
        )
        critique = ask_reviewer_manual(critique_input, r)
        transcript.append((f"Round {r} — Reviewer (Claude)", critique))

        user_msg = (
            f"Voici la critique de ton reviewer:\n\n{critique}\n\n"
            f"Propose une version révisée des setups [REFINE], "
            f"garde tels quels les [BACKTEST_NOW]."
        )

    return transcript, critique


def save_transcript(topic: str, transcript: list) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    safe_topic = re.sub(r"[^\w\-]+", "_", topic)[:60]
    path = HISTORY_DIR / f"{timestamp}_{safe_topic}.md"
    with path.open("w") as f:
        f.write(f"# Collab session — {topic}\n\n")
        f.write(f"_Date: {dt.datetime.now().isoformat(timespec='seconds')}_\n\n")
        for title, content in transcript:
            f.write(f"## {title}\n\n{content}\n\n---\n\n")
    return path


def extract_backtest_items(final_critique: str) -> list:
    """Parse [BACKTEST_NOW] sections from the final critique."""
    items = []
    pattern = re.compile(
        r"##\s*Setup:\s*(.+?)\n(.*?)(?=\n##\s*Setup:|\Z)",
        re.DOTALL,
    )
    for match in pattern.finditer(final_critique):
        name = match.group(1).strip()
        block = match.group(2)
        if "[BACKTEST_NOW]" in block:
            items.append({"name": name, "spec": block.strip()})
    return items


def append_to_queue(items: list, topic: str, transcript_path: Path):
    if not items:
        return
    BACKTEST_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if BACKTEST_QUEUE.exists():
        existing = json.loads(BACKTEST_QUEUE.read_text())
    for item in items:
        existing.append({
            "added_at": dt.datetime.now().isoformat(timespec="seconds"),
            "topic": topic,
            "transcript": str(transcript_path),
            "status": "pending",
            **item,
        })
    BACKTEST_QUEUE.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="Collab: ChatGPT propose, Claude critique, tu arbitres."
    )
    parser.add_argument("topic", help="Sujet de la session (entre guillemets)")
    parser.add_argument("--rounds", type=int, default=1, help="Nombre de tours (défaut 1)")
    parser.add_argument(
        "--mode",
        choices=["manual", "api"],
        default="manual",
        help="manual = copier-coller (utilise ton ChatGPT Pro), api = appels directs",
    )
    parser.add_argument("--gpt-model", default="gpt-5", help="Modèle OpenAI (mode api)")
    parser.add_argument(
        "--claude-model",
        default="claude-opus-4-7",
        help="Modèle Anthropic (mode api)",
    )
    args = parser.parse_args()

    if args.mode == "api":
        if not os.getenv("OPENAI_API_KEY"):
            sys.exit("Erreur: OPENAI_API_KEY manquant. Mets-le dans .env ou exporte-le.")
        if not os.getenv("ANTHROPIC_API_KEY"):
            sys.exit("Erreur: ANTHROPIC_API_KEY manquant.")
        transcript, final_critique = run_api_mode(
            args.topic, args.rounds, args.gpt_model, args.claude_model
        )
    else:
        transcript, final_critique = run_manual_mode(args.topic, args.rounds)

    path = save_transcript(args.topic, transcript)
    print(f"\nTranscript sauvegardé: {path}")

    items = extract_backtest_items(final_critique)
    if items:
        append_to_queue(items, args.topic, path)
        print(f"{len(items)} setup(s) ajouté(s) à {BACKTEST_QUEUE}:")
        for it in items:
            print(f"  - {it['name']}")
    else:
        print("Aucun setup tagué [BACKTEST_NOW] dans la critique finale.")
