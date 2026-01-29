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
import re
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
    spin_speed_ratio: float = 1.0


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


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y", "是", "对", "t"}:
        return True
    if raw in {"0", "false", "no", "n", "否", "错", "f"}:
        return False
    raise ValueError(f"无法解析布尔值: {value}")


def _parse_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raw = str(value).strip()
    if raw == "":
        return None
    return int(raw)


def _parse_speed_ratio(value: Any, default: float = 1.0) -> float:
    if value is None or value == "":
        return default
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return default
    if ratio < 0.1 or ratio > 5:
        return default
    return ratio


def _split_ids(raw: str) -> List[str]:
    if not raw:
        return []
    return [item for item in re.split(r"[;,，\s]+", raw) if item]


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return base_dir / raw_path


def _read_people_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "id": row.get("id", "").strip(),
                "name": row.get("name", "").strip(),
                "department": row.get("department", "").strip(),
            }
            for row in reader
            if any(row.values())
        ]


def _read_prizes_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        data: List[Dict[str, Any]] = []
        for row in reader:
            if not any(row.values()):
                continue
            must_win_ids = _split_ids(str(row.get("must_win_ids", "")).strip())
            data.append(
                {
                    "id": str(row.get("id", "")).strip(),
                    "name": str(row.get("name", "")).strip(),
                    "count": int(row.get("count", 0) or 0),
                    "exclude_previous_winners": _parse_bool(row.get("exclude_previous_winners", True)),
                    "exclude_must_win": _parse_bool(row.get("exclude_must_win", True)),
                    "exclude_excluded_list": _parse_bool(row.get("exclude_excluded_list", True)),
                    "must_win_ids": must_win_ids,
                    "spin_speed_ratio": _parse_speed_ratio(row.get("spin_speed_ratio", 1.0)),
                }
            )
        return data


def _write_people_csv(path: Path, payload: Iterable[Dict[str, Any]]) -> None:
    fieldnames = ["id", "name", "department"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_prizes_csv(path: Path, payload: Iterable[Dict[str, Any]]) -> None:
    fieldnames = [
        "id",
        "name",
        "count",
        "exclude_previous_winners",
        "exclude_must_win",
        "exclude_excluded_list",
        "must_win_ids",
        "spin_speed_ratio",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload:
            writer.writerow(
                {
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "count": row.get("count", ""),
                    "exclude_previous_winners": row.get("exclude_previous_winners", True),
                    "exclude_must_win": row.get("exclude_must_win", True),
                    "exclude_excluded_list": row.get("exclude_excluded_list", True),
                    "must_win_ids": ",".join(row.get("must_win_ids", [])),
                    "spin_speed_ratio": row.get("spin_speed_ratio", 1.0),
                }
            )


def read_people_data(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return _read_people_csv(path)
    return read_json(path)


def read_prizes_data(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return _read_prizes_csv(path)
    return read_json(path)


def read_excluded_data(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return read_people_data(path)


def write_people_data(path: Path, payload: Iterable[Dict[str, Any]]) -> None:
    if path.suffix.lower() == ".csv":
        _write_people_csv(path, payload)
    else:
        write_json(path, list(payload))


def write_prizes_data(path: Path, payload: Iterable[Dict[str, Any]]) -> None:
    if path.suffix.lower() == ".csv":
        _write_prizes_csv(path, payload)
    else:
        write_json(path, list(payload))


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
    raw_people = read_people_data(path)
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
                spin_speed_ratio=_parse_speed_ratio(entry.get("spin_speed_ratio", 1.0)),
            )
        )
    return prizes


def load_prizes(path: Path) -> List[PrizeConfig]:
    raw_prizes = read_prizes_data(path)
    return parse_prize_entries(raw_prizes)


def load_excluded_people(path: Path) -> List[Person]:
    raw_people = read_excluded_data(path)
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
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
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
    include_excluded: bool = False,
    excluded_winner_range: tuple[int | None, int | None] | None = None,
    prizes: Optional[List[PrizeConfig]] = None,
    draw_count: int | None = None,
) -> List[Dict[str, Any]]:
    prize_state = state["prizes"].setdefault(prize.prize_id, {"winners": []})
    existing_prize_winners = set(prize_state["winners"])
    existing_global_winners = {winner["person_id"] for winner in state["winners"]}
    excluded_ids = excluded_ids or set()
    exclude_excluded_list = prize.exclude_excluded_list and not include_excluded
    if not exclude_excluded_list:
        exclusion_blocklist = set()
    else:
        exclusion_blocklist = set(excluded_ids)

    remaining = remaining_slots(prize, state)
    if remaining <= 0:
        return []
    if draw_count is not None:
        if draw_count < 0:
            raise ValueError("抽奖人数不能为负数。")
        remaining = min(remaining, draw_count)

    excluded_winners = existing_global_winners if prize.exclude_previous_winners else set()
    excluded_must_win = global_must_win if prize.exclude_must_win else set()
    excluded_must_win = excluded_must_win - set(prize.must_win_ids)

    eligible_people = [
        person
        for person in people
        if person.person_id not in excluded_winners
        and person.person_id not in excluded_must_win
        and person.person_id not in existing_prize_winners
        and person.person_id not in exclusion_blocklist
    ]

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    excluded_selected_count = 0

    for must_id in prize.must_win_ids:
        if remaining <= len(selected):
            break
        if must_id in existing_prize_winners:
            continue
        if exclude_excluded_list and must_id in excluded_ids:
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
        if match.person_id in excluded_ids:
            excluded_selected_count += 1

    remaining = remaining - len(selected)
    if remaining > 0:
        apply_excluded_range = (
            excluded_winner_range is not None
            and not include_excluded
            and prizes is not None
        )
        if apply_excluded_range:
            prize_lookup = {item.prize_id: item for item in prizes}
            total_remaining_slots = sum(remaining_slots(item, state) for item in prizes)
            remaining_slots_after = total_remaining_slots - remaining
            existing_applicable_total = sum(
                1
                for entry in state["winners"]
                if prize_lookup.get(entry["prize_id"])
            )
            existing_excluded_total = sum(
                1
                for entry in state["winners"]
                if entry["person_id"] in excluded_ids
                and prize_lookup.get(entry["prize_id"])
            )
            min_excluded, max_excluded = excluded_winner_range
            min_excluded = 0 if min_excluded is None else min_excluded
            if min_excluded < 0:
                raise ValueError("排除名单最小中奖人数不能为负数。")
            if max_excluded is not None and max_excluded < 0:
                raise ValueError("排除名单最大中奖人数不能为负数。")
            if max_excluded is not None and max_excluded < min_excluded:
                raise ValueError("排除名单最大中奖人数不能小于最小值。")
            current_excluded_total = existing_excluded_total + excluded_selected_count
            if max_excluded is not None and current_excluded_total > max_excluded:
                raise ValueError("排除名单中奖人数已超过最大限制。")

            excluded_pool = [
                person
                for person in eligible_people
                if person.person_id in excluded_ids and person.person_id not in selected_ids
            ]
            non_excluded_pool = [
                person
                for person in eligible_people
                if person.person_id not in excluded_ids and person.person_id not in selected_ids
            ]

            min_needed_total = max(min_excluded - current_excluded_total, 0)
            min_needed_in_current = max(min_needed_total - remaining_slots_after, 0)
            if min_needed_in_current > remaining:
                raise ValueError("排除名单最小中奖人数超过可抽取名额。")
            if min_needed_in_current > len(excluded_pool):
                raise ValueError("排除名单人数不足，无法满足最小中奖人数要求。")

            if max_excluded is not None:
                max_additional_excluded = max_excluded - current_excluded_total
                if max_additional_excluded < 0:
                    raise ValueError("排除名单中奖人数已超过最大限制。")
            else:
                max_additional_excluded = remaining

            min_non_excluded_needed = max(remaining - len(excluded_pool), 0)
            max_excluded_allowed = min(
                max_additional_excluded,
                remaining - min_non_excluded_needed,
                len(excluded_pool),
            )
            min_excluded_allowed = min_needed_in_current
            if existing_applicable_total == 0 and non_excluded_pool and min_excluded_allowed < remaining:
                max_excluded_allowed = min(max_excluded_allowed, remaining - 1)
            if min_excluded_allowed > max_excluded_allowed:
                raise ValueError("候选人不足，无法满足排除名单中奖人数范围。")
            excluded_count = (
                min_excluded_allowed
                if min_excluded_allowed == max_excluded_allowed
                else random.randint(min_excluded_allowed, max_excluded_allowed)
            )
            non_excluded_needed = remaining - excluded_count
            if non_excluded_needed > len(non_excluded_pool):
                raise ValueError("非排除名单人数不足，无法满足最大中奖人数限制。")

            if excluded_count:
                for person in random.sample(excluded_pool, excluded_count):
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
                    excluded_selected_count += 1

            if non_excluded_needed:
                for person in random.sample(non_excluded_pool, non_excluded_needed):
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
        else:
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
    excluded_file = resolve_path(base_dir, config.get("excluded_file", "data/excluded.csv"))
    output_dir = resolve_path(base_dir, config.get("output_dir", "output"))
    results_file = config.get("results_file", "results.json")
    results_csv = config.get("results_csv", "results.csv")
    try:
        excluded_winners_min = _parse_optional_int(config.get("excluded_winners_min"))
        excluded_winners_max = _parse_optional_int(config.get("excluded_winners_max"))
    except ValueError as exc:
        raise SystemExit(f"排除名单中奖人数配置错误: {exc}") from exc

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
    try:
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
                selected_total.extend(
                    draw_prize(
                        prize,
                        people,
                        state,
                        global_must_win,
                        excluded_ids,
                        include_excluded=args.include_excluded,
                        excluded_winner_range=(excluded_winners_min, excluded_winners_max),
                        prizes=prizes,
                    )
                )
        elif args.command == "draw-all":
            for prize in prizes:
                selected_total.extend(
                    draw_prize(
                        prize,
                        people,
                        state,
                        global_must_win,
                        excluded_ids,
                        include_excluded=args.include_excluded,
                        excluded_winner_range=(excluded_winners_min, excluded_winners_max),
                        prizes=prizes,
                    )
                )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

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
