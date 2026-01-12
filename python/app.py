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

        self.people = load_people(self.participants_file)
        self.prizes = load_prizes(self.prizes_file)
        self.excluded_people = load_excluded_people(self.excluded_file)
        self.state = load_state(self.state_path)
        self.global_must_win = build_global_must_win(self.prizes)

        self.seed_var = tk.StringVar()
        self.prize_var = tk.StringVar()
        self.include_excluded_var = tk.BooleanVar(value=False)
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
                    "must_win_ids": [],
                },
                {
                    "id": "P002",
                    "name": "二等奖",
                    "count": 1,
                    "exclude_previous_winners": True,
                    "exclude_must_win": True,
                    "must_win_ids": ["U1006"],
                },
                {
                    "id": "P003",
                    "name": "一等奖",
                    "count": 1,
                    "exclude_previous_winners": True,
                    "exclude_must_win": False,
                    "must_win_ids": [],
                },
            ]
            with prizes_path.open("w", encoding="utf-8") as handle:
                json.dump(prizes, handle, ensure_ascii=False, indent=2)

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
        info_frame = ttk.Frame(parent, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="人员名单文件:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.participants_path_var).pack(anchor=tk.W)

        self.participants_text = tk.Text(parent, height=18, wrap=tk.NONE)
        self.participants_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._load_people_editor()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="保存名单", command=self._save_people).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载名单", command=self._load_people_editor).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入名单", command=self._import_people).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出名单", command=self._export_people).pack(side=tk.LEFT, padx=5)

    def _build_prizes_editor(self, parent: ttk.Frame) -> None:
        info_frame = ttk.Frame(parent, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="奖项配置文件:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.prizes_path_var).pack(anchor=tk.W)

        self.prizes_text = tk.Text(parent, height=18, wrap=tk.NONE)
        self.prizes_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._load_prizes_editor()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="保存奖项", command=self._save_prizes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载奖项", command=self._load_prizes_editor).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入奖项", command=self._import_prizes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出奖项", command=self._export_prizes).pack(side=tk.LEFT, padx=5)

    def _build_excluded_editor(self, parent: ttk.Frame) -> None:
        info_frame = ttk.Frame(parent, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="排查名单文件:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.excluded_path_var).pack(anchor=tk.W)

        self.excluded_text = tk.Text(parent, height=18, wrap=tk.NONE)
        self.excluded_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._load_excluded_editor()

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="保存排查名单", command=self._save_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载排查名单", command=self._load_excluded_editor).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入排查名单", command=self._import_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出排查名单", command=self._export_excluded).pack(side=tk.LEFT, padx=5)

    def _load_json_editor(self, text_widget: tk.Text, path: Path) -> None:
        try:
            data = read_json(path)
        except FileNotFoundError:
            data = []
        except json.JSONDecodeError as exc:
            messagebox.showerror("读取失败", f"无法读取 {path}: {exc}")
            return
        text_widget.delete("1.0", tk.END)
        text_widget.insert(tk.END, json.dumps(data, ensure_ascii=False, indent=2))

    def _parse_editor_json(self, text_widget: tk.Text) -> Any:
        raw = text_widget.get("1.0", tk.END).strip()
        if not raw:
            return []
        return json.loads(raw)

    def _save_json_editor(
        self,
        text_widget: tk.Text,
        path: Path,
        validator: Callable[[Any], Any] | None = None,
    ) -> Any:
        try:
            data = self._parse_editor_json(text_widget)
        except json.JSONDecodeError as exc:
            messagebox.showerror("保存失败", f"JSON 无效: {exc}")
            return None
        if validator:
            try:
                validator(data)
            except ValueError as exc:
                messagebox.showerror("保存失败", str(exc))
                return None
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    def _import_json_editor(self, text_widget: tk.Text, validator: Callable[[Any], Any] | None = None) -> None:
        path = filedialog.askopenfilename(title="选择要导入的 JSON 文件", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        path_obj = Path(path)
        try:
            data = read_json(path_obj)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            messagebox.showerror("导入失败", f"无法读取 {path_obj}: {exc}")
            return
        if validator:
            try:
                validator(data)
            except ValueError as exc:
                messagebox.showerror("导入失败", str(exc))
                return
        text_widget.delete("1.0", tk.END)
        text_widget.insert(tk.END, json.dumps(data, ensure_ascii=False, indent=2))

    def _export_json_editor(self, text_widget: tk.Text, validator: Callable[[Any], Any] | None = None) -> None:
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        data = self._save_json_editor(text_widget, Path(path), validator=validator)
        if data is not None:
            messagebox.showinfo("导出完成", f"已导出到 {path}")

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

        selected = draw_prize(
            prize,
            self.people,
            self.state,
            self.global_must_win,
            self._current_excluded_ids(),
        )
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
        for prize in self.prizes:
            selected_total.extend(
                draw_prize(
                    prize,
                    self.people,
                    self.state,
                    self.global_must_win,
                    self._current_excluded_ids(),
                )
            )
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

    def _load_config_editor(self) -> None:
        self.config_text.delete("1.0", tk.END)
        self.config_text.insert(tk.END, json.dumps(self.config, ensure_ascii=False, indent=2))

    def _load_people_editor(self) -> None:
        self._load_json_editor(self.participants_text, self.participants_file)

    def _load_prizes_editor(self) -> None:
        self._load_json_editor(self.prizes_text, self.prizes_file)

    def _load_excluded_editor(self) -> None:
        self._load_json_editor(self.excluded_text, self.excluded_file)

    def _save_people(self) -> None:
        data = self._save_json_editor(self.participants_text, self.participants_file, parse_people_entries)
        if data is None:
            return
        self.people = parse_people_entries(data)
        messagebox.showinfo("成功", "人员名单已保存。")

    def _save_prizes(self) -> None:
        data = self._save_json_editor(self.prizes_text, self.prizes_file, parse_prize_entries)
        if data is None:
            return
        self.prizes = parse_prize_entries(data)
        self.global_must_win = build_global_must_win(self.prizes)
        self._refresh_prizes()
        messagebox.showinfo("成功", "奖项配置已保存。")

    def _save_excluded(self) -> None:
        data = self._save_json_editor(self.excluded_text, self.excluded_file, parse_people_entries)
        if data is None:
            return
        self.excluded_people = parse_people_entries(data)
        messagebox.showinfo("成功", "排查名单已保存。")

    def _import_people(self) -> None:
        self._import_json_editor(self.participants_text, parse_people_entries)

    def _import_prizes(self) -> None:
        self._import_json_editor(self.prizes_text, parse_prize_entries)

    def _import_excluded(self) -> None:
        self._import_json_editor(self.excluded_text, parse_people_entries)

    def _export_people(self) -> None:
        self._export_json_editor(self.participants_text, parse_people_entries)

    def _export_prizes(self) -> None:
        self._export_json_editor(self.prizes_text, parse_prize_entries)

    def _export_excluded(self) -> None:
        self._export_json_editor(self.excluded_text, parse_people_entries)

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
        self._load_people_editor()
        self._load_prizes_editor()
        self._load_excluded_editor()
        self._refresh_prizes()
        self._refresh_winners()
        messagebox.showinfo("完成", "配置与数据已重新加载。")


def main() -> None:
    config_path = Path("python/config.json")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    root = tk.Tk()
    app = LotteryApp(root, config_path)
    root.mainloop()


if __name__ == "__main__":
    main()
