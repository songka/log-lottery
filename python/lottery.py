#!/usr/bin/env python3
"""Simple local lottery runner.

Usage examples:
  python python/lottery.py draw-all
  python python/lottery.py draw --prize P002
  python python/lottery.py show
  python python/lottery.py reset
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class PrizeConfig:
    prize_id: str
    name: str
    count: int
    exclude_previous_winners: bool
    exclude_must_win: bool
    exclude_excluded_list: bool
    must_win_ids: List[str]


@dataclass
class Person:
    person_id: str
    name: str
    department: str


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return base_dir / raw_path


def parse_people_entries(raw_people: Iterable[Dict[str, Any]]) -> List[Person]:
    if not isinstance(raw_people, list):
        raise ValueError("Participants data must be a list of objects.")
    people = []
    seen_ids = set()
    for entry in raw_people:
        person_id = str(entry.get("id", "")).strip()
        name = str(entry.get("name", "")).strip()
        if not person_id or not name:
            raise ValueError(f"Invalid participant entry: {entry}")
        if person_id in seen_ids:
            raise ValueError(f"Duplicate participant id: {person_id}")
        seen_ids.add(person_id)
        department = str(entry.get("department", "")).strip()
        if not department:
            raise ValueError(f"Invalid participant entry (missing department): {entry}")
        people.append(Person(person_id=person_id, name=name, department=department))
    return people


def load_people(path: Path) -> List[Person]:
    raw_people = read_json(path)
    return parse_people_entries(raw_people)


def parse_prize_entries(raw_prizes: Iterable[Dict[str, Any]]) -> List[PrizeConfig]:
    if not isinstance(raw_prizes, list):
        raise ValueError("Prizes data must be a list of objects.")
    prizes = []
    seen_ids = set()
    for entry in raw_prizes:
        prize_id = str(entry.get("id", "")).strip()
        name = str(entry.get("name", "")).strip()
        count = int(entry.get("count", 0))
        if not prize_id or not name or count <= 0:
            raise ValueError(f"Invalid prize entry: {entry}")
        if prize_id in seen_ids:
            raise ValueError(f"Duplicate prize id: {prize_id}")
        seen_ids.add(prize_id)
        prizes.append(
            PrizeConfig(
                prize_id=prize_id,
                name=name,
                count=count,
                exclude_previous_winners=bool(entry.get("exclude_previous_winners", True)),
                exclude_must_win=bool(entry.get("exclude_must_win", True)),
                exclude_excluded_list=bool(entry.get("exclude_excluded_list", True)),
                must_win_ids=[str(item) for item in entry.get("must_win_ids", [])],
            )
        )
    return prizes


def load_prizes(path: Path) -> List[PrizeConfig]:
    raw_prizes = read_json(path)
    return parse_prize_entries(raw_prizes)


def load_excluded_people(path: Path) -> List[Person]:
    if not path.exists():
        return []
    raw_people = read_json(path)
    return parse_people_entries(raw_people)


def load_state(state_path: Path) -> Dict[str, Any]:
    if state_path.exists():
        return read_json(state_path)
    return {
        "version": 1,
        "generated_at": utc_now(),
        "winners": [],
        "prizes": {},
    }


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def save_state(state_path: Path, state: Dict[str, Any]) -> None:
    state["generated_at"] = utc_now()
    write_json(state_path, state)


def save_csv(csv_path: Path, winners: Iterable[Dict[str, Any]]) -> None:
    fieldnames = [
        "timestamp",
        "prize_id",
        "prize_name",
        "person_id",
        "person_name",
        "department",
        "source",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for winner in winners:
            writer.writerow({key: winner.get(key, "") for key in fieldnames})


def build_global_must_win(prizes: List[PrizeConfig]) -> set[str]:
    must_win = set()
    for prize in prizes:
        must_win.update(prize.must_win_ids)
    return must_win


def remaining_slots(prize: PrizeConfig, state: Dict[str, Any]) -> int:
    prize_state = state["prizes"].setdefault(prize.prize_id, {"winners": []})
    return prize.count - len(prize_state["winners"])


def available_prizes(prizes: List[PrizeConfig], state: Dict[str, Any]) -> List[PrizeConfig]:
    return [prize for prize in prizes if remaining_slots(prize, state) > 0]


def draw_prize(
    prize: PrizeConfig,
    people: List[Person],
    state: Dict[str, Any],
    global_must_win: set[str],
    excluded_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    prize_state = state["prizes"].setdefault(prize.prize_id, {"winners": []})
    existing_prize_winners = set(prize_state["winners"])
    existing_global_winners = {winner["person_id"] for winner in state["winners"]}
    excluded_ids = excluded_ids or set()
    if not prize.exclude_excluded_list:
        excluded_ids = set()

    remaining = remaining_slots(prize, state)
    if remaining <= 0:
        return []

    excluded_winners = existing_global_winners if prize.exclude_previous_winners else set()
    excluded_must_win = global_must_win if prize.exclude_must_win else set()
    excluded_must_win = excluded_must_win - set(prize.must_win_ids)

    eligible_people = [
        person
        for person in people
        if person.person_id not in excluded_winners
        and person.person_id not in excluded_must_win
        and person.person_id not in existing_prize_winners
        and person.person_id not in excluded_ids
    ]

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    for must_id in prize.must_win_ids:
        if must_id in existing_prize_winners:
            continue
        if must_id in excluded_ids:
            continue
        match = next((person for person in people if person.person_id == must_id), None)
        if not match:
            continue
        selected.append(
            {
                "timestamp": utc_now(),
                "prize_id": prize.prize_id,
                "prize_name": prize.name,
                "person_id": match.person_id,
                "person_name": match.name,
                "department": match.department,
                "source": "must_win",
            }
        )
        selected_ids.add(match.person_id)

    remaining = prize.count - len(existing_prize_winners) - len(selected)
    if remaining > 0:
        random_pool = [person for person in eligible_people if person.person_id not in selected_ids]
        if remaining > len(random_pool):
            remaining = len(random_pool)
        for person in random.sample(random_pool, remaining):
            selected.append(
                {
                    "timestamp": utc_now(),
                    "prize_id": prize.prize_id,
                    "prize_name": prize.name,
                    "person_id": person.person_id,
                    "person_name": person.name,
                    "department": person.department,
                    "source": "random",
                }
            )
            selected_ids.add(person.person_id)

    for entry in selected:
        state["winners"].append(entry)
        prize_state["winners"].append(entry["person_id"])

    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local lottery runner (Python version).")
    parser.add_argument(
        "--config",
        default="python/config.json",
        help="Path to config.json (default: python/config.json)",
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducible draws")
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="Include the excluded list when drawing winners",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw_parser = subparsers.add_parser("draw", help="Draw winners for a single prize")
    draw_parser.add_argument("--prize", required=True, help="Prize ID to draw")

    subparsers.add_parser("draw-all", help="Draw winners for all prizes")
    subparsers.add_parser("show", help="Show current winners")
    subparsers.add_parser("reset", help="Clear local draw results")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    config_path = Path(args.config)
    base_dir = config_path.parent
    config = read_json(config_path)

    participants_file = resolve_path(base_dir, config["participants_file"])
    prizes_file = resolve_path(base_dir, config["prizes_file"])
    excluded_file = resolve_path(base_dir, config.get("excluded_file", "data/excluded.json"))
    output_dir = resolve_path(base_dir, config.get("output_dir", "output"))
    results_file = config.get("results_file", "results.json")
    results_csv = config.get("results_csv", "results.csv")

    ensure_output_dir(output_dir)
    state_path = output_dir / results_file
    csv_path = output_dir / results_csv

    if args.command == "reset":
        save_state(state_path, {"version": 1, "generated_at": utc_now(), "winners": [], "prizes": {}})
        save_csv(csv_path, [])
        print(f"已清空结果: {state_path}")
        return

    people = load_people(participants_file)
    prizes = load_prizes(prizes_file)
    state = load_state(state_path)
    global_must_win = build_global_must_win(prizes)
    excluded_people = load_excluded_people(excluded_file)
    excluded_ids = {person.person_id for person in excluded_people}

    if args.command == "show":
        if not state["winners"]:
            print("暂无中奖记录。")
            return
        for winner in state["winners"]:
            print(
                f"{winner['timestamp']} | {winner['prize_name']} | {winner['person_name']}"
                f" ({winner['person_id']}) [{winner['source']}]"
            )
        return

    selected_total: List[Dict[str, Any]] = []
    if args.command == "draw":
        prize = next((item for item in prizes if item.prize_id == args.prize), None)
        if not prize:
            raise SystemExit(f"未找到奖项: {args.prize}")
        remaining = remaining_slots(prize, state)
        if remaining <= 0:
            available = [item for item in prizes if remaining_slots(item, state) > 0]
            if available:
                options = "，".join(f"{item.prize_id}({item.name})" for item in available)
                raise SystemExit(f"奖项已抽完: {args.prize}。可抽奖项: {options}")
            raise SystemExit("所有奖项已抽完，无可抽奖项。")
        selected_total.extend(draw_prize(prize, people, state, global_must_win, excluded_ids))
    elif args.command == "draw-all":
        for prize in prizes:
            selected_total.extend(draw_prize(prize, people, state, global_must_win, excluded_ids))

    save_state(state_path, state)
    save_csv(csv_path, state["winners"])

    if not selected_total:
        print("本次未抽出新的中奖名单。")
        return

    print("本次中奖名单:")
    for entry in selected_total:
        print(
            f"- {entry['prize_name']} | {entry['person_name']} ({entry['person_id']}) [{entry['source']}]"
        )


if __name__ == "__main__":
    main()
