#!/usr/bin/env python3
"""Tkinter UI for the local lottery runner."""

from __future__ import annotations

import json
import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from lottery import (
    available_prizes,
    build_global_must_win,
    draw_prize,
    load_excluded_people,
    load_people,
    load_prizes,
    load_state,
    parse_people_entries,
    parse_prize_entries,
    read_json,
    remaining_slots,
    resolve_path,
    save_csv,
    save_state,
    utc_now,
)


class LotteryApp:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.root.title("log-lottery (Python)")
        self.config_path = config_path
        self.base_dir = config_path.parent

        self._ensure_default_files()
        self.config = self._load_config()
        self.participants_file = resolve_path(self.base_dir, self.config["participants_file"])
        self.prizes_file = resolve_path(self.base_dir, self.config["prizes_file"])
        self.excluded_file = resolve_path(self.base_dir, self.config.get("excluded_file", "data/excluded.json"))
        self.output_dir = resolve_path(self.base_dir, self.config.get("output_dir", "output"))
        self.results_file = self.config.get("results_file", "results.json")
        self.results_csv = self.config.get("results_csv", "results.csv")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / self.results_file
        self.csv_path = self.output_dir / self.results_csv

        self.people_data = self._load_people_data()
        self.prizes_data = self._load_prizes_data()
        self.excluded_data = self._load_excluded_data()
        self.people = load_people(self.participants_file)
        self.prizes = load_prizes(self.prizes_file)
        self.excluded_people = load_excluded_people(self.excluded_file)
        self.state = load_state(self.state_path)
        self.global_must_win = build_global_must_win(self.prizes)

        self.seed_var = tk.StringVar()
        self.prize_var = tk.StringVar()
        self.participants_path_var = tk.StringVar(value=str(self.participants_file))
        self.prizes_path_var = tk.StringVar(value=str(self.prizes_file))
        self.excluded_path_var = tk.StringVar(value=str(self.excluded_file))
        self.output_dir_var = tk.StringVar(value=str(self.output_dir))

        self._build_ui()
        self._refresh_prizes()
        self._refresh_winners()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            messagebox.showerror("配置错误", f"未找到配置文件: {self.config_path}")
            raise SystemExit(1)
        return read_json(self.config_path)

    def _ensure_default_files(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            default_config = {
                "participants_file": "data/participants.json",
                "prizes_file": "data/prizes.json",
                "excluded_file": "data/excluded.json",
                "output_dir": "output",
                "results_file": "results.json",
                "results_csv": "results.csv",
            }
            with self.config_path.open("w", encoding="utf-8") as handle:
                json.dump(default_config, handle, ensure_ascii=False, indent=2)

        data_dir = self.base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        participants_path = data_dir / "participants.json"
        if not participants_path.exists():
            participants = [
                {"id": "U1001", "name": "张三", "department": "研发"},
                {"id": "U1002", "name": "李四", "department": "产品"},
                {"id": "U1003", "name": "王五", "department": "设计"},
                {"id": "U1004", "name": "赵六", "department": "运营"},
                {"id": "U1005", "name": "钱七", "department": "市场"},
                {"id": "U1006", "name": "孙八", "department": "财务"},
            ]
            with participants_path.open("w", encoding="utf-8") as handle:
                json.dump(participants, handle, ensure_ascii=False, indent=2)

        excluded_path = data_dir / "excluded.json"
        if not excluded_path.exists():
            with excluded_path.open("w", encoding="utf-8") as handle:
                json.dump([], handle, ensure_ascii=False, indent=2)

        prizes_path = data_dir / "prizes.json"
        if not prizes_path.exists():
            prizes = [
                {
                    "id": "P001",
                    "name": "三等奖",
                    "count": 2,
                    "exclude_previous_winners": True,
                    "exclude_must_win": True,
                    "exclude_excluded_list": True,
                    "must_win_ids": [],
                },
                {
                    "id": "P002",
                    "name": "二等奖",
                    "count": 1,
                    "exclude_previous_winners": True,
                    "exclude_must_win": True,
                    "exclude_excluded_list": True,
                    "must_win_ids": ["U1006"],
                },
                {
                    "id": "P003",
                    "name": "一等奖",
                    "count": 1,
                    "exclude_previous_winners": True,
                    "exclude_must_win": False,
                    "exclude_excluded_list": True,
                    "must_win_ids": [],
                },
            ]
            with prizes_path.open("w", encoding="utf-8") as handle:
                json.dump(prizes, handle, ensure_ascii=False, indent=2)

    def _load_people_data(self) -> list[dict[str, Any]]:
        try:
            data = read_json(self.participants_file)
        except FileNotFoundError:
            return []
        return data

    def _load_prizes_data(self) -> list[dict[str, Any]]:
        try:
            data = read_json(self.prizes_file)
        except FileNotFoundError:
            return []
        return data

    def _load_excluded_data(self) -> list[dict[str, Any]]:
        try:
            data = read_json(self.excluded_file)
        except FileNotFoundError:
            return []
        return data

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.main_frame = ttk.Frame(notebook)
        self.config_frame = ttk.Frame(notebook)
        notebook.add(self.main_frame, text="主界面")
        notebook.add(self.config_frame, text="配置")

        self._build_main_tab()
        self._build_config_tab()

    def _build_main_tab(self) -> None:
        top_frame = ttk.Frame(self.main_frame, padding=10)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="随机种子 (可选):").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(top_frame, textvariable=self.seed_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="选择奖项:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.prize_combo = ttk.Combobox(top_frame, textvariable=self.prize_var, state="readonly", width=24)
        self.prize_combo.grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Checkbutton(
            top_frame,
            text="不排除排查名单",
            variable=self.include_excluded_var,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(5, 0))

        button_frame = ttk.Frame(self.main_frame, padding=10)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="抽取当前奖项", command=self._draw_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="抽取全部奖项", command=self._draw_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="刷新名单", command=self._refresh_winners).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置结果", command=self._reset_results).pack(side=tk.LEFT, padx=5)

        self.output_text = tk.Text(self.main_frame, height=16, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _build_config_tab(self) -> None:
        notebook = ttk.Notebook(self.config_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        config_tab = ttk.Frame(notebook)
        participants_tab = ttk.Frame(notebook)
        prizes_tab = ttk.Frame(notebook)
        excluded_tab = ttk.Frame(notebook)

        notebook.add(config_tab, text="配置文件")
        notebook.add(participants_tab, text="人员名单")
        notebook.add(prizes_tab, text="奖项配置")
        notebook.add(excluded_tab, text="排查名单")

        self._build_config_editor(config_tab)
        self._build_people_editor(participants_tab)
        self._build_prizes_editor(prizes_tab)
        self._build_excluded_editor(excluded_tab)

    def _build_config_editor(self, parent: ttk.Frame) -> None:
        info_frame = ttk.Frame(parent, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=f"配置文件: {self.config_path}").pack(anchor=tk.W)
        ttk.Label(info_frame, text="人员名单:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.participants_path_var).pack(anchor=tk.W)
        ttk.Label(info_frame, text="奖项配置:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.prizes_path_var).pack(anchor=tk.W)
        ttk.Label(info_frame, text="排查名单:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.excluded_path_var).pack(anchor=tk.W)
        ttk.Label(info_frame, text="结果输出:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.output_dir_var).pack(anchor=tk.W)

        self.config_text = tk.Text(parent, height=18, wrap=tk.NONE)
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._load_config_editor()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="保存配置", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载配置", command=self._reload_all).pack(side=tk.LEFT, padx=5)

    def _build_people_editor(self, parent: ttk.Frame) -> None:
        self.people_tree = ttk.Treeview(parent, columns=("id", "name", "department"), show="headings", height=12)
        for col, label, width in (
            ("id", "工号", 120),
            ("name", "姓名", 120),
            ("department", "部门", 120),
        ):
            self.people_tree.heading(col, text=label)
            self.people_tree.column(col, width=width, anchor=tk.W)
        self.people_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._refresh_people_tree()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="新增", command=self._add_person).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="修改", command=self._edit_person).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除", command=self._delete_person).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="上移", command=self._move_person_up).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="下移", command=self._move_person_down).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入", command=self._import_people).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出", command=self._export_people).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存", command=self._save_people).pack(side=tk.LEFT, padx=5)

    def _build_prizes_editor(self, parent: ttk.Frame) -> None:
        self.prizes_tree = ttk.Treeview(
            parent,
            columns=(
                "id",
                "name",
                "count",
                "exclude_previous_winners",
                "exclude_must_win",
                "exclude_excluded_list",
                "must_win_ids",
            ),
            show="headings",
            height=12,
        )
        headings = (
            ("id", "奖项ID", 90),
            ("name", "奖项名称", 120),
            ("count", "数量", 60),
            ("exclude_previous_winners", "排除已中奖", 90),
            ("exclude_must_win", "排除保底", 90),
            ("exclude_excluded_list", "排除排查名单", 110),
            ("must_win_ids", "保底工号", 160),
        )
        for col, label, width in headings:
            self.prizes_tree.heading(col, text=label)
            self.prizes_tree.column(col, width=width, anchor=tk.W)
        self.prizes_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._refresh_prizes_tree()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="新增", command=self._add_prize).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="修改", command=self._edit_prize).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除", command=self._delete_prize).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="上移", command=self._move_prize_up).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="下移", command=self._move_prize_down).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入", command=self._import_prizes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出", command=self._export_prizes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存", command=self._save_prizes).pack(side=tk.LEFT, padx=5)

    def _build_excluded_editor(self, parent: ttk.Frame) -> None:
        self.excluded_tree = ttk.Treeview(parent, columns=("id", "name", "department"), show="headings", height=12)
        for col, label, width in (
            ("id", "工号", 120),
            ("name", "姓名", 120),
            ("department", "部门", 120),
        ):
            self.excluded_tree.heading(col, text=label)
            self.excluded_tree.column(col, width=width, anchor=tk.W)
        self.excluded_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._refresh_excluded_tree()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="新增", command=self._add_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="修改", command=self._edit_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除", command=self._delete_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="上移", command=self._move_excluded_up).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="下移", command=self._move_excluded_down).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入", command=self._import_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出", command=self._export_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存", command=self._save_excluded).pack(side=tk.LEFT, padx=5)

    def _load_config_editor(self) -> None:
        self.config_text.delete("1.0", tk.END)
        self.config_text.insert(tk.END, json.dumps(self.config, ensure_ascii=False, indent=2))

    def _save_config(self) -> None:
        raw = self.config_text.get("1.0", tk.END).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            messagebox.showerror("配置错误", f"配置 JSON 无效: {exc}")
            return
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        messagebox.showinfo("成功", "配置已保存，请点击重新加载配置生效。")

    def _set_seed(self) -> None:
        seed = self.seed_var.get().strip()
        if seed:
            try:
                random.seed(int(seed))
            except ValueError:
                messagebox.showerror("种子错误", "随机种子必须是整数。")
                raise

    def _refresh_prizes(self) -> None:
        available = available_prizes(self.prizes, self.state)
        options = [f"{prize.prize_id} - {prize.name} (剩余 {remaining_slots(prize, self.state)})" for prize in available]
        self.prize_combo["values"] = options
        if options:
            if self.prize_var.get() not in options:
                self.prize_var.set(options[0])
        else:
            self.prize_var.set("")

    def _append_output(self, text: str) -> None:
        self.output_text.insert(tk.END, text + "\n")
        self.output_text.see(tk.END)

    def _refresh_winners(self) -> None:
        self.output_text.delete("1.0", tk.END)
        if not self.state["winners"]:
            self._append_output("暂无中奖记录。")
            return
        for winner in self.state["winners"]:
            self._append_output(
                f"{winner['timestamp']} | {winner['prize_name']} | {winner['person_name']} "
                f"({winner['person_id']}) [{winner['source']}]"
            )

    def _current_excluded_ids(self) -> set[str]:
        if self.include_excluded_var.get():
            return set()
        return {person.person_id for person in self.excluded_people}

    def _persist_state(self) -> None:
        save_state(self.state_path, self.state)
        save_csv(self.csv_path, self.state["winners"])

    def _draw_selected(self) -> None:
        try:
            self._set_seed()
        except ValueError:
            return

        selected_label = self.prize_var.get().strip()
        if not selected_label:
            messagebox.showwarning("提示", "当前没有可抽奖项。")
            return
        prize_id = selected_label.split(" - ", 1)[0]
        prize = next((item for item in self.prizes if item.prize_id == prize_id), None)
        if not prize:
            messagebox.showerror("错误", f"未找到奖项: {prize_id}")
            return
        if remaining_slots(prize, self.state) <= 0:
            messagebox.showwarning("提示", "该奖项已抽完，请选择其他奖项。")
            self._refresh_prizes()
            return

        excluded_ids = {person.person_id for person in self.excluded_people}
        selected = draw_prize(prize, self.people, self.state, self.global_must_win, excluded_ids)
        self._persist_state()
        self._refresh_prizes()

        if not selected:
            self._append_output("本次未抽出新的中奖名单。")
            return
        self._append_output("本次中奖名单:")
        for entry in selected:
            self._append_output(
                f"- {entry['prize_name']} | {entry['person_name']} ({entry['person_id']}) [{entry['source']}]"
            )

    def _draw_all(self) -> None:
        try:
            self._set_seed()
        except ValueError:
            return
        selected_total = []
        excluded_ids = {person.person_id for person in self.excluded_people}
        for prize in self.prizes:
            selected_total.extend(draw_prize(prize, self.people, self.state, self.global_must_win, excluded_ids))
        self._persist_state()
        self._refresh_prizes()
        if not selected_total:
            self._append_output("本次未抽出新的中奖名单。")
            return
        self._append_output("本次中奖名单:")
        for entry in selected_total:
            self._append_output(
                f"- {entry['prize_name']} | {entry['person_name']} ({entry['person_id']}) [{entry['source']}]"
            )

    def _reset_results(self) -> None:
        if not messagebox.askyesno("确认", "确定要清空所有中奖结果吗？"):
            return
        self.state = {"version": 1, "generated_at": utc_now(), "winners": [], "prizes": {}}
        self._persist_state()
        self._refresh_prizes()
        self._refresh_winners()

    def _reload_all(self) -> None:
        self.config = self._load_config()
        self.participants_file = resolve_path(self.base_dir, self.config["participants_file"])
        self.prizes_file = resolve_path(self.base_dir, self.config["prizes_file"])
        self.excluded_file = resolve_path(self.base_dir, self.config.get("excluded_file", "data/excluded.json"))
        self.output_dir = resolve_path(self.base_dir, self.config.get("output_dir", "output"))
        self.results_file = self.config.get("results_file", "results.json")
        self.results_csv = self.config.get("results_csv", "results.csv")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / self.results_file
        self.csv_path = self.output_dir / self.results_csv

        self.people_data = self._load_people_data()
        self.prizes_data = self._load_prizes_data()
        self.excluded_data = self._load_excluded_data()
        self.people = load_people(self.participants_file)
        self.prizes = load_prizes(self.prizes_file)
        self.excluded_people = load_excluded_people(self.excluded_file)
        self.state = load_state(self.state_path)
        self.global_must_win = build_global_must_win(self.prizes)

        self.participants_path_var.set(str(self.participants_file))
        self.prizes_path_var.set(str(self.prizes_file))
        self.excluded_path_var.set(str(self.excluded_file))
        self.output_dir_var.set(str(self.output_dir))
        self._load_config_editor()
        self._refresh_people_tree()
        self._refresh_prizes_tree()
        self._refresh_excluded_tree()
        self._refresh_prizes()
        self._refresh_winners()
        messagebox.showinfo("完成", "配置与数据已重新加载。")

    def _refresh_people_tree(self) -> None:
        self.people_tree.delete(*self.people_tree.get_children())
        for index, person in enumerate(self.people_data):
            self.people_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(person.get("id", ""), person.get("name", ""), person.get("department", "")),
            )

    def _refresh_prizes_tree(self) -> None:
        self.prizes_tree.delete(*self.prizes_tree.get_children())
        for index, prize in enumerate(self.prizes_data):
            self.prizes_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    prize.get("id", ""),
                    prize.get("name", ""),
                    prize.get("count", ""),
                    "是" if prize.get("exclude_previous_winners", True) else "否",
                    "是" if prize.get("exclude_must_win", True) else "否",
                    "是" if prize.get("exclude_excluded_list", True) else "否",
                    ",".join(prize.get("must_win_ids", [])),
                ),
            )

    def _refresh_excluded_tree(self) -> None:
        self.excluded_tree.delete(*self.excluded_tree.get_children())
        for index, person in enumerate(self.excluded_data):
            self.excluded_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(person.get("id", ""), person.get("name", ""), person.get("department", "")),
            )

    def _selected_index(self, tree: ttk.Treeview) -> int | None:
        selection = tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def _open_person_dialog(self, title: str, initial: dict[str, Any] | None = None) -> dict[str, Any] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()

        person_id_var = tk.StringVar(value="" if initial is None else str(initial.get("id", "")))
        name_var = tk.StringVar(value="" if initial is None else str(initial.get("name", "")))
        department_var = tk.StringVar(value="" if initial is None else str(initial.get("department", "")))

        ttk.Label(dialog, text="工号:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=person_id_var).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(dialog, text="姓名:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=name_var).grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(dialog, text="部门:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=department_var).grid(row=2, column=1, padx=10, pady=5)

        result: dict[str, Any] | None = None

        def on_ok() -> None:
            person_id = person_id_var.get().strip()
            name = name_var.get().strip()
            department = department_var.get().strip()
            if not person_id or not name or not department:
                messagebox.showerror("错误", "工号、姓名、部门不能为空。", parent=dialog)
                return
            nonlocal result
            result = {"id": person_id, "name": name, "department": department}
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, padding=10)
        button_frame.grid(row=3, column=0, columnspan=2)
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.wait_window()
        return result

    def _open_prize_dialog(self, title: str, initial: dict[str, Any] | None = None) -> dict[str, Any] | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.grab_set()

        prize_id_var = tk.StringVar(value="" if initial is None else str(initial.get("id", "")))
        name_var = tk.StringVar(value="" if initial is None else str(initial.get("name", "")))
        count_var = tk.StringVar(value="" if initial is None else str(initial.get("count", "")))
        must_win_var = tk.StringVar(
            value="" if initial is None else ",".join(initial.get("must_win_ids", []))
        )
        exclude_previous_var = tk.BooleanVar(
            value=True if initial is None else bool(initial.get("exclude_previous_winners", True))
        )
        exclude_must_win_var = tk.BooleanVar(
            value=True if initial is None else bool(initial.get("exclude_must_win", True))
        )
        exclude_excluded_var = tk.BooleanVar(
            value=True if initial is None else bool(initial.get("exclude_excluded_list", True))
        )

        ttk.Label(dialog, text="奖项ID:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=prize_id_var).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(dialog, text="奖项名称:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=name_var).grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(dialog, text="数量:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=count_var).grid(row=2, column=1, padx=10, pady=5)
        ttk.Label(dialog, text="保底工号(逗号分隔):").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        ttk.Entry(dialog, textvariable=must_win_var).grid(row=3, column=1, padx=10, pady=5)
        ttk.Checkbutton(dialog, text="排除已中奖", variable=exclude_previous_var).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, padx=10
        )
        ttk.Checkbutton(dialog, text="排除保底名单", variable=exclude_must_win_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=10
        )
        ttk.Checkbutton(dialog, text="排除排查名单", variable=exclude_excluded_var).grid(
            row=6, column=0, columnspan=2, sticky=tk.W, padx=10
        )

        result: dict[str, Any] | None = None

        def on_ok() -> None:
            prize_id = prize_id_var.get().strip()
            name = name_var.get().strip()
            count_raw = count_var.get().strip()
            if not prize_id or not name or not count_raw:
                messagebox.showerror("错误", "奖项ID、名称、数量不能为空。", parent=dialog)
                return
            try:
                count = int(count_raw)
            except ValueError:
                messagebox.showerror("错误", "数量必须是整数。", parent=dialog)
                return
            must_win_ids = [item.strip() for item in must_win_var.get().split(",") if item.strip()]
            nonlocal result
            result = {
                "id": prize_id,
                "name": name,
                "count": count,
                "exclude_previous_winners": exclude_previous_var.get(),
                "exclude_must_win": exclude_must_win_var.get(),
                "exclude_excluded_list": exclude_excluded_var.get(),
                "must_win_ids": must_win_ids,
            }
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, padding=10)
        button_frame.grid(row=7, column=0, columnspan=2)
        ttk.Button(button_frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=5)

        dialog.wait_window()
        return result

    def _apply_people_change(self, new_data: list[dict[str, Any]]) -> bool:
        try:
            parse_people_entries(new_data)
        except ValueError as exc:
            messagebox.showerror("错误", str(exc))
            return False
        self.people_data = new_data
        self._refresh_people_tree()
        return True

    def _apply_excluded_change(self, new_data: list[dict[str, Any]]) -> bool:
        try:
            parse_people_entries(new_data)
        except ValueError as exc:
            messagebox.showerror("错误", str(exc))
            return False
        self.excluded_data = new_data
        self._refresh_excluded_tree()
        return True

    def _apply_prizes_change(self, new_data: list[dict[str, Any]]) -> bool:
        try:
            parse_prize_entries(new_data)
        except ValueError as exc:
            messagebox.showerror("错误", str(exc))
            return False
        self.prizes_data = new_data
        self._refresh_prizes_tree()
        return True

    def _add_person(self) -> None:
        result = self._open_person_dialog("新增人员")
        if result is None:
            return
        new_data = [*self.people_data, result]
        self._apply_people_change(new_data)

    def _edit_person(self) -> None:
        index = self._selected_index(self.people_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要修改的人员。")
            return
        result = self._open_person_dialog("修改人员", self.people_data[index])
        if result is None:
            return
        new_data = self.people_data.copy()
        new_data[index] = result
        self._apply_people_change(new_data)

    def _delete_person(self) -> None:
        index = self._selected_index(self.people_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要删除的人员。")
            return
        new_data = self.people_data.copy()
        del new_data[index]
        self._apply_people_change(new_data)

    def _move_person_up(self) -> None:
        index = self._selected_index(self.people_tree)
        if index is None or index == 0:
            return
        new_data = self.people_data.copy()
        new_data[index - 1], new_data[index] = new_data[index], new_data[index - 1]
        if self._apply_people_change(new_data):
            self.people_tree.selection_set(str(index - 1))

    def _move_person_down(self) -> None:
        index = self._selected_index(self.people_tree)
        if index is None or index >= len(self.people_data) - 1:
            return
        new_data = self.people_data.copy()
        new_data[index + 1], new_data[index] = new_data[index], new_data[index + 1]
        if self._apply_people_change(new_data):
            self.people_tree.selection_set(str(index + 1))

    def _add_excluded(self) -> None:
        result = self._open_person_dialog("新增排查人员")
        if result is None:
            return
        new_data = [*self.excluded_data, result]
        self._apply_excluded_change(new_data)

    def _edit_excluded(self) -> None:
        index = self._selected_index(self.excluded_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要修改的排查人员。")
            return
        result = self._open_person_dialog("修改排查人员", self.excluded_data[index])
        if result is None:
            return
        new_data = self.excluded_data.copy()
        new_data[index] = result
        self._apply_excluded_change(new_data)

    def _delete_excluded(self) -> None:
        index = self._selected_index(self.excluded_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要删除的排查人员。")
            return
        new_data = self.excluded_data.copy()
        del new_data[index]
        self._apply_excluded_change(new_data)

    def _move_excluded_up(self) -> None:
        index = self._selected_index(self.excluded_tree)
        if index is None or index == 0:
            return
        new_data = self.excluded_data.copy()
        new_data[index - 1], new_data[index] = new_data[index], new_data[index - 1]
        if self._apply_excluded_change(new_data):
            self.excluded_tree.selection_set(str(index - 1))

    def _move_excluded_down(self) -> None:
        index = self._selected_index(self.excluded_tree)
        if index is None or index >= len(self.excluded_data) - 1:
            return
        new_data = self.excluded_data.copy()
        new_data[index + 1], new_data[index] = new_data[index], new_data[index + 1]
        if self._apply_excluded_change(new_data):
            self.excluded_tree.selection_set(str(index + 1))

    def _add_prize(self) -> None:
        result = self._open_prize_dialog("新增奖项")
        if result is None:
            return
        new_data = [*self.prizes_data, result]
        self._apply_prizes_change(new_data)

    def _edit_prize(self) -> None:
        index = self._selected_index(self.prizes_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要修改的奖项。")
            return
        result = self._open_prize_dialog("修改奖项", self.prizes_data[index])
        if result is None:
            return
        new_data = self.prizes_data.copy()
        new_data[index] = result
        self._apply_prizes_change(new_data)

    def _delete_prize(self) -> None:
        index = self._selected_index(self.prizes_tree)
        if index is None:
            messagebox.showwarning("提示", "请选择需要删除的奖项。")
            return
        new_data = self.prizes_data.copy()
        del new_data[index]
        self._apply_prizes_change(new_data)

    def _move_prize_up(self) -> None:
        index = self._selected_index(self.prizes_tree)
        if index is None or index == 0:
            return
        new_data = self.prizes_data.copy()
        new_data[index - 1], new_data[index] = new_data[index], new_data[index - 1]
        if self._apply_prizes_change(new_data):
            self.prizes_tree.selection_set(str(index - 1))

    def _move_prize_down(self) -> None:
        index = self._selected_index(self.prizes_tree)
        if index is None or index >= len(self.prizes_data) - 1:
            return
        new_data = self.prizes_data.copy()
        new_data[index + 1], new_data[index] = new_data[index], new_data[index + 1]
        if self._apply_prizes_change(new_data):
            self.prizes_tree.selection_set(str(index + 1))

    def _save_people(self) -> None:
        if not self._apply_people_change(self.people_data):
            return
        with self.participants_file.open("w", encoding="utf-8") as handle:
            json.dump(self.people_data, handle, ensure_ascii=False, indent=2)
        self.people = parse_people_entries(self.people_data)
        messagebox.showinfo("成功", "人员名单已保存。")

    def _save_prizes(self) -> None:
        if not self._apply_prizes_change(self.prizes_data):
            return
        with self.prizes_file.open("w", encoding="utf-8") as handle:
            json.dump(self.prizes_data, handle, ensure_ascii=False, indent=2)
        self.prizes = parse_prize_entries(self.prizes_data)
        self.global_must_win = build_global_must_win(self.prizes)
        self._refresh_prizes()
        messagebox.showinfo("成功", "奖项配置已保存。")

    def _save_excluded(self) -> None:
        if not self._apply_excluded_change(self.excluded_data):
            return
        with self.excluded_file.open("w", encoding="utf-8") as handle:
            json.dump(self.excluded_data, handle, ensure_ascii=False, indent=2)
        self.excluded_people = parse_people_entries(self.excluded_data)
        messagebox.showinfo("成功", "排查名单已保存。")

    def _import_json_list(
        self,
        validator: Callable[[list[dict[str, Any]]], Any],
    ) -> list[dict[str, Any]] | None:
        path = filedialog.askopenfilename(title="选择要导入的 JSON 文件", filetypes=[("JSON files", "*.json")])
        if not path:
            return None
        path_obj = Path(path)
        try:
            data = read_json(path_obj)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            messagebox.showerror("导入失败", f"无法读取 {path_obj}: {exc}")
            return None
        try:
            validator(data)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return None
        return data

    def _export_json_list(self, data: list[dict[str, Any]]) -> None:
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        messagebox.showinfo("导出完成", f"已导出到 {path}")

    def _import_people(self) -> None:
        data = self._import_json_list(parse_people_entries)
        if data is None:
            return
        self._apply_people_change(data)

    def _export_people(self) -> None:
        self._export_json_list(self.people_data)

    def _import_prizes(self) -> None:
        data = self._import_json_list(parse_prize_entries)
        if data is None:
            return
        self._apply_prizes_change(data)

    def _export_prizes(self) -> None:
        self._export_json_list(self.prizes_data)

    def _import_excluded(self) -> None:
        data = self._import_json_list(parse_people_entries)
        if data is None:
            return
        self._apply_excluded_change(data)

    def _export_excluded(self) -> None:
        self._export_json_list(self.excluded_data)


def main() -> None:
    config_path = Path("python/config.json")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    root = tk.Tk()
    app = LotteryApp(root, config_path)
    root.mainloop()


if __name__ == "__main__":
    main()
