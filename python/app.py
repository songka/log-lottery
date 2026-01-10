#!/usr/bin/env python3
"""Tkinter UI for the local lottery runner."""

from __future__ import annotations

import json
import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from lottery import (
    available_prizes,
    build_global_must_win,
    draw_prize,
    load_people,
    load_prizes,
    load_state,
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

        self.config = self._load_config()
        self.participants_file = resolve_path(self.base_dir, self.config["participants_file"])
        self.prizes_file = resolve_path(self.base_dir, self.config["prizes_file"])
        self.output_dir = resolve_path(self.base_dir, self.config.get("output_dir", "output"))
        self.results_file = self.config.get("results_file", "results.json")
        self.results_csv = self.config.get("results_csv", "results.csv")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / self.results_file
        self.csv_path = self.output_dir / self.results_csv

        self.people = load_people(self.participants_file)
        self.prizes = load_prizes(self.prizes_file)
        self.state = load_state(self.state_path)
        self.global_must_win = build_global_must_win(self.prizes)

        self.seed_var = tk.StringVar()
        self.prize_var = tk.StringVar()

        self._build_ui()
        self._refresh_prizes()
        self._refresh_winners()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            messagebox.showerror("配置错误", f"未找到配置文件: {self.config_path}")
            raise SystemExit(1)
        return read_json(self.config_path)

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

        button_frame = ttk.Frame(self.main_frame, padding=10)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="抽取当前奖项", command=self._draw_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="抽取全部奖项", command=self._draw_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="刷新名单", command=self._refresh_winners).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重置结果", command=self._reset_results).pack(side=tk.LEFT, padx=5)

        self.output_text = tk.Text(self.main_frame, height=16, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _build_config_tab(self) -> None:
        info_frame = ttk.Frame(self.config_frame, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=f"配置文件: {self.config_path}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"人员名单: {self.participants_file}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"奖项配置: {self.prizes_file}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"结果输出: {self.output_dir}").pack(anchor=tk.W)

        self.config_text = tk.Text(self.config_frame, height=18, wrap=tk.NONE)
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._load_config_editor()

        button_frame = ttk.Frame(self.config_frame, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="保存配置", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载配置", command=self._reload_all).pack(side=tk.LEFT, padx=5)

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

        selected = draw_prize(prize, self.people, self.state, self.global_must_win)
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
            selected_total.extend(draw_prize(prize, self.people, self.state, self.global_must_win))
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
        self.output_dir = resolve_path(self.base_dir, self.config.get("output_dir", "output"))
        self.results_file = self.config.get("results_file", "results.json")
        self.results_csv = self.config.get("results_csv", "results.csv")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.output_dir / self.results_file
        self.csv_path = self.output_dir / self.results_csv
        self.people = load_people(self.participants_file)
        self.prizes = load_prizes(self.prizes_file)
        self.state = load_state(self.state_path)
        self.global_must_win = build_global_must_win(self.prizes)
        self._load_config_editor()
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
