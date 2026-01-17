#!/usr/bin/env python3
"""Tkinter UI for the local lottery runner."""

from __future__ import annotations

import copy
import json
import math
import random
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any

from visual_window import VisualLotteryWindow
from wheel_window import WheelLotteryWindow

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
    read_excluded_data,
    read_people_data,
    read_prizes_data,
    read_json,
    remaining_slots,
    resolve_path,
    save_csv,
    save_state,
    utc_now,
    write_people_data,
    write_prizes_data,
)


class LotteryApp:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.root.title("log-lottery (Python)")
        self.config_path = config_path
        self.base_dir = config_path.parent

        self._ensure_default_files()
        self.config = self._load_config()
        self.admin_password = str(self.config.get("admin_password", ""))
        self.is_admin = False
        self.participants_file = resolve_path(self.base_dir, self.config["participants_file"])
        self.prizes_file = resolve_path(self.base_dir, self.config["prizes_file"])
        self.excluded_file = resolve_path(self.base_dir, self.config.get("excluded_file", "data/excluded.csv"))
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
        self.config_path_var = tk.StringVar(value=str(self.config_path))
        self.participants_path_var = tk.StringVar(value=str(self.participants_file))
        self.prizes_path_var = tk.StringVar(value=str(self.prizes_file))
        self.excluded_path_var = tk.StringVar(value=str(self.excluded_file))
        self.output_dir_var = tk.StringVar(value=str(self.output_dir))
        self.include_excluded_var = tk.BooleanVar(value=False)
        self.login_status_var = tk.StringVar(value="未登录")
        self.draw_window = None
        self.draw_canvas = None
        self.draw_phase = "idle"
        self.draw_speed = 0.0
        self.draw_angle = 0.0
        self.draw_items: list[dict[str, Any]] = []
        self.draw_after_id = None
        self.draw_selected_prize_id = None
        self.pending_state: dict[str, Any] | None = None
        self.pending_winners: list[dict[str, Any]] = []
        self.last_space_time = 0.0
        self.visual_window = None
        # Wheel window is a separate draw experience with multi-stop suspense.
        self.wheel_window = None

        self._build_ui()
        self._update_login_state()
        self._refresh_prizes()
        self._refresh_winners()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            messagebox.showerror("配置错误", f"未找到配置文件: {self.config_path}")
            raise SystemExit(1)
        config = read_json(self.config_path)
        config.setdefault("visual_background_color", "#0b0f1c")
        config.setdefault("visual_background", "")
        config.setdefault("visual_music", "")
        config.setdefault("win_sound", "win.mp3")
        config.setdefault("visual_screen_x", 0)
        config.setdefault("visual_screen_y", 0)
        config.setdefault("visual_screen_width", 0)
        config.setdefault("visual_screen_height", 0)
        return config

    def _ensure_default_files(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            default_config = {
                "participants_file": "data/participants.csv",
                "prizes_file": "data/prizes.csv",
                "excluded_file": "data/excluded.csv",
                "output_dir": "output",
                "results_file": "results.json",
                "results_csv": "results.csv",
                "admin_password": "admin",
                "visual_background_color": "#0b0f1c",
                "visual_background": "",
                "visual_music": "",
                "win_sound": "win.mp3",
                "visual_screen_x": 0,
                "visual_screen_y": 0,
                "visual_screen_width": 0,
                "visual_screen_height": 0,
            }
            with self.config_path.open("w", encoding="utf-8") as handle:
                json.dump(default_config, handle, ensure_ascii=False, indent=2)

        data_dir = self.base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        participants_path = data_dir / "participants.csv"
        if not participants_path.exists():
            participants = [
                {"id": "U1001", "name": "张三", "department": "研发"},
                {"id": "U1002", "name": "李四", "department": "产品"},
                {"id": "U1003", "name": "王五", "department": "设计"},
                {"id": "U1004", "name": "赵六", "department": "运营"},
                {"id": "U1005", "name": "钱七", "department": "市场"},
                {"id": "U1006", "name": "孙八", "department": "财务"},
            ]
            write_people_data(participants_path, participants)

        excluded_path = data_dir / "excluded.csv"
        if not excluded_path.exists():
            write_people_data(excluded_path, [])

        prizes_path = data_dir / "prizes.csv"
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
            write_prizes_data(prizes_path, prizes)

    def _load_people_data(self) -> list[dict[str, Any]]:
        try:
            data = read_people_data(self.participants_file)
        except FileNotFoundError:
            return []
        return data

    def _load_prizes_data(self) -> list[dict[str, Any]]:
        try:
            data = read_prizes_data(self.prizes_file)
        except FileNotFoundError:
            return []
        return data

    def _load_excluded_data(self) -> list[dict[str, Any]]:
        try:
            data = read_excluded_data(self.excluded_file)
        except FileNotFoundError:
            return []
        return data

    def _build_ui(self) -> None:
        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.pack(fill=tk.BOTH, expand=True)

        self.main_frame = ttk.Frame(self.main_notebook)
        self.config_tab = ttk.Frame(self.main_notebook)
        self.participants_tab = ttk.Frame(self.main_notebook)
        self.prizes_tab = ttk.Frame(self.main_notebook)
        self.excluded_tab = ttk.Frame(self.main_notebook)

        self.main_notebook.add(self.main_frame, text="主界面")
        self.main_notebook.add(self.config_tab, text="配置文件")
        self.main_notebook.add(self.participants_tab, text="人员名单")
        self.main_notebook.add(self.prizes_tab, text="奖项配置")
        self.main_notebook.add(self.excluded_tab, text="排查名单")

        self._build_main_tab()
        self._build_config_editor(self.config_tab)
        self._build_people_editor(self.participants_tab)
        self._build_prizes_editor(self.prizes_tab)
        self._build_excluded_editor(self.excluded_tab)

    def _build_main_tab(self) -> None:
        header_frame = ttk.Frame(self.main_frame, padding=10)
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="抽奖中心", font=("Helvetica", 16, "bold")).pack(anchor=tk.W)

        settings_frame = ttk.LabelFrame(self.main_frame, text="抽奖设置", padding=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(settings_frame, text="随机种子 (可选):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(settings_frame, textvariable=self.seed_var, width=20).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=2
        )

        ttk.Label(settings_frame, text="选择奖项:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.prize_combo = ttk.Combobox(settings_frame, textvariable=self.prize_var, state="readonly", width=24)
        self.prize_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        ttk.Checkbutton(
            settings_frame,
            text="不排除排查名单",
            variable=self.include_excluded_var,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(6, 0))

        action_frame = ttk.Frame(self.main_frame, padding=10)
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="抽取当前奖项", command=self._draw_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="抽取全部奖项", command=self._draw_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="打开抽奖界面", command=self._open_draw_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="转盘抽奖", command=self._open_wheel_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="开启大屏模式", command=self._open_visual_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="大屏设置", command=self._open_visual_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="刷新名单", command=self._refresh_winners).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="重置结果", command=self._reset_results).pack(side=tk.LEFT, padx=5)

        output_frame = ttk.LabelFrame(self.main_frame, text="中奖名单", padding=10)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.output_text = tk.Text(output_frame, height=16, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True)

    def _build_config_editor(self, parent: ttk.Frame) -> None:
        info_frame = ttk.Frame(parent, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="配置文件:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.config_path_var).pack(anchor=tk.W)
        ttk.Label(info_frame, text="人员名单:").pack(anchor=tk.W)
        self.participants_path_label = ttk.Label(info_frame, textvariable=self.participants_path_var)
        self.participants_path_label.pack(anchor=tk.W)
        ttk.Label(info_frame, text="奖项配置:").pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.prizes_path_var).pack(anchor=tk.W)
        self.excluded_label = ttk.Label(info_frame, text="排查名单:")
        self.excluded_label.pack(anchor=tk.W)
        self.excluded_path_label = ttk.Label(info_frame, textvariable=self.excluded_path_var)
        self.excluded_path_label.pack(anchor=tk.W)
        self.output_label = ttk.Label(info_frame, text="结果输出:")
        self.output_label.pack(anchor=tk.W)
        ttk.Label(info_frame, textvariable=self.output_dir_var).pack(anchor=tk.W)
        ttk.Label(info_frame, text="登录状态:").pack(anchor=tk.W, pady=(10, 0))
        ttk.Label(info_frame, textvariable=self.login_status_var).pack(anchor=tk.W)

        button_frame = ttk.Frame(parent, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="选择配置文件", command=self._select_config_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="选择人员名单", command=self._select_participants_file).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="选择奖项配置", command=self._select_prizes_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="选择输出目录", command=self._select_output_dir).pack(side=tk.LEFT, padx=5)
        self.excluded_select_button = ttk.Button(
            button_frame, text="选择排查名单", command=self._select_excluded_file
        )
        ttk.Button(button_frame, text="登录/退出", command=self._toggle_login).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新加载配置", command=self._reload_all).pack(side=tk.LEFT, padx=5)
        self._update_config_visibility()

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
        self.prize_columns_basic = ("id", "name", "count", "exclude_previous_winners")
        self.prize_columns_admin = (
            "id",
            "name",
            "count",
            "exclude_previous_winners",
            "exclude_must_win",
            "exclude_excluded_list",
            "must_win_ids",
        )
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
        self._update_prize_columns()
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
        self.excluded_admin_frame = ttk.Frame(parent)

        self.excluded_tree = ttk.Treeview(
            self.excluded_admin_frame, columns=("id", "name", "department"), show="headings", height=12
        )
        for col, label, width in (
            ("id", "工号", 120),
            ("name", "姓名", 120),
            ("department", "部门", 120),
        ):
            self.excluded_tree.heading(col, text=label)
            self.excluded_tree.column(col, width=width, anchor=tk.W)
        self.excluded_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self._refresh_excluded_tree()

        button_frame = ttk.Frame(self.excluded_admin_frame, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="新增", command=self._add_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="修改", command=self._edit_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除", command=self._delete_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="上移", command=self._move_excluded_up).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="下移", command=self._move_excluded_down).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导入", command=self._import_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="导出", command=self._export_excluded).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存", command=self._save_excluded).pack(side=tk.LEFT, padx=5)
        self._update_excluded_visibility()

    def _select_config_file(self) -> None:
        path = filedialog.askopenfilename(title="选择配置文件", filetypes=[("JSON files", "*.json")])
        if not path:
            return
        self.config_path = Path(path)
        self.base_dir = self.config_path.parent
        self.config_path_var.set(str(self.config_path))
        self._reload_all()

    def _relative_or_absolute(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.base_dir))
        except ValueError:
            return str(path)

    def _save_config_file(self) -> None:
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(self.config, handle, ensure_ascii=False, indent=2)

    def _select_participants_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择人员名单文件",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        self.config["participants_file"] = self._relative_or_absolute(Path(path))
        self._save_config_file()
        self._reload_all()

    def _select_prizes_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择奖项配置文件",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        self.config["prizes_file"] = self._relative_or_absolute(Path(path))
        self._save_config_file()
        self._reload_all()

    def _select_excluded_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择排查名单文件",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        self.config["excluded_file"] = self._relative_or_absolute(Path(path))
        self._save_config_file()
        self._reload_all()

    def _select_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if not path:
            return
        self.config["output_dir"] = self._relative_or_absolute(Path(path))
        self._save_config_file()
        self._reload_all()

    def _toggle_login(self) -> None:
        if self.is_admin:
            self.is_admin = False
            self._update_login_state()
            return
        if not self.admin_password:
            messagebox.showerror("提示", "请先在配置文件中设置 admin_password。")
            return
        password = simpledialog.askstring("登录", "请输入管理员密码：", show="*")
        if password is None:
            return
        if password != self.admin_password:
            messagebox.showerror("错误", "密码错误。")
            return
        self.is_admin = True
        self._update_login_state()

    def _update_login_state(self) -> None:
        self.login_status_var.set("已登录" if self.is_admin else "未登录")
        self._update_prize_columns()
        self._refresh_prizes_tree()
        self._update_config_visibility()
        self._update_excluded_visibility()

    def _update_prize_columns(self) -> None:
        if not hasattr(self, "prizes_tree"):
            return
        display = self.prize_columns_admin if self.is_admin else self.prize_columns_basic
        self.prizes_tree["displaycolumns"] = display

    def _update_excluded_visibility(self) -> None:
        if not hasattr(self, "excluded_admin_frame"):
            return
        if hasattr(self, "main_notebook") and hasattr(self, "excluded_tab"):
            self.main_notebook.tab(self.excluded_tab, state="normal" if self.is_admin else "hidden")
        if self.is_admin:
            self.excluded_admin_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.excluded_admin_frame.pack_forget()

    def _update_config_visibility(self) -> None:
        if not hasattr(self, "excluded_label"):
            return
        if self.is_admin:
            if not self.excluded_label.winfo_ismapped():
                self.excluded_label.pack(anchor=tk.W, before=self.output_label)
            if not self.excluded_path_label.winfo_ismapped():
                self.excluded_path_label.pack(anchor=tk.W, before=self.output_label)
            if hasattr(self, "excluded_select_button") and not self.excluded_select_button.winfo_ismapped():
                self.excluded_select_button.pack(side=tk.LEFT, padx=5)
        else:
            self.excluded_label.pack_forget()
            self.excluded_path_label.pack_forget()
            if hasattr(self, "excluded_select_button"):
                self.excluded_select_button.pack_forget()

    def _open_draw_window(self) -> None:
        if self.draw_window and self.draw_window.winfo_exists():
            self.draw_window.lift()
            return
        self.draw_window = tk.Toplevel(self.root)
        self.draw_window.title("抽奖界面")
        self.draw_window.geometry("1200x700")
        self.draw_window.protocol("WM_DELETE_WINDOW", self._close_draw_window)
        self.draw_window.bind("<space>", self._handle_space)

        container = ttk.Frame(self.draw_window)
        container.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(container, width=260)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(left_panel, text="奖项列表", font=("Helvetica", 12, "bold")).pack(anchor=tk.W, pady=(0, 6))
        self.draw_prize_list = tk.Listbox(left_panel, height=12)
        self.draw_prize_list.pack(fill=tk.X)
        self.draw_prize_list.bind("<<ListboxSelect>>", self._on_draw_prize_select)
        self._refresh_draw_prize_list()

        self.draw_prize_info = ttk.Label(left_panel, text="请选择奖项")
        self.draw_prize_info.pack(anchor=tk.W, pady=(6, 0))

        center_panel = ttk.Frame(container)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.draw_canvas = tk.Canvas(center_panel, bg="#1f2230", highlightthickness=0)
        self.draw_canvas.pack(fill=tk.BOTH, expand=True)

        right_panel = ttk.Frame(container, width=260)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(right_panel, text="控制面板", font=("Helvetica", 12, "bold")).pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(right_panel, text="进入抽奖", command=self._enter_draw).pack(fill=tk.X, pady=4)
        ttk.Button(right_panel, text="开始", command=self._start_spin).pack(fill=tk.X, pady=4)
        ttk.Button(right_panel, text="抽取幸运儿", command=self._draw_lucky).pack(fill=tk.X, pady=4)
        ttk.Button(right_panel, text="转存该次抽奖", command=self._transfer_draw).pack(fill=tk.X, pady=4)

        ttk.Label(
            right_panel, text="空格可触发动作 (每次间隔>=1秒)", foreground="#888"
        ).pack(anchor=tk.W, pady=(10, 0))

        self._build_idle_grid()

    def _close_draw_window(self) -> None:
        if self.draw_after_id and self.draw_canvas:
            self.draw_canvas.after_cancel(self.draw_after_id)
            self.draw_after_id = None
        if self.draw_window and self.draw_window.winfo_exists():
            self.draw_window.destroy()
        self.draw_window = None
        self.draw_canvas = None
    def _open_wheel_window(self) -> None:
        """打开转盘抽奖窗口，并确保数据完整"""
        # 1. 检查窗口是否已打开
        if hasattr(self, "wheel_window") and self.wheel_window and self.wheel_window.winfo_exists():
            self.wheel_window.lift()
            return

        # 2. 准备数据：确保所有必要的变量都已存在
        # 如果 self.excluded_ids 不存在，则从加载函数获取
        excluded_ids = getattr(self, "excluded_ids", None)
        if excluded_ids is None:
            # 尝试重新加载一次全局排查名单
            excluded_ids = load_excluded_people(resolve_path(self.base_dir, self.config["excluded_file"]))
        
        # 重新同步一次最新的状态和奖项
        self.prizes = load_prizes(resolve_path(self.base_dir, self.config["prizes_file"]))
        self.state = load_state(resolve_path(self.base_dir, self.config["output_dir"]) / self.config["results_file"])
        global_must_win = build_global_must_win(self.prizes)

        # 3. 获取主界面当前选中的奖项ID
        current_prize_id = None
        current_val = self.prize_combo.get()
        if current_val:
             current_prize_id = current_val.split(" - ")[0]

        # 4. 创建转盘窗口
        self.wheel_window = WheelLotteryWindow(
            root=self.root,
            prizes=self.prizes,
            people=self.people,
            state=self.state,
            global_must_win=global_must_win,
            excluded_ids=excluded_ids,
            on_transfer=self._handle_transfer_from_window,
            on_close=lambda: setattr(self, "wheel_window", None),
        )
        
        # 5. 如果主界面有选中奖项，立即同步给转盘
        if current_prize_id:
            self.wheel_window.select_prize_by_id(current_prize_id)
    # 修改主界面的奖项选择回调
    def _on_prize_selected(self, event: tk.Event) -> None:
        """Handle prize selection in the main dropdown."""
        # 原有的逻辑保持不变...
        val = self.prize_combo.get()
        if not val:
            return
        prize_id = val.split(" - ")[0]
        
        # 新增逻辑：如果转盘窗口开着，通知它切换奖项
        if hasattr(self, "wheel_window") and self.wheel_window and self.wheel_window.winfo_exists():
            self.wheel_window.select_prize_by_id(prize_id)
            
    def _on_wheel_transfer(self, state: dict[str, Any], winners: list[dict[str, Any]]) -> None:
        """Persist wheel results back into the main application state."""
        if not winners:
            return
        self.state = state
        self._persist_state()
        self._refresh_prizes()
        self._refresh_winners()
        self._refresh_draw_prize_list()

    def _on_wheel_closed(self) -> None:
        self.wheel_window = None

    def _open_visual_window(self) -> None:
        if self.visual_window and self.visual_window.winfo_exists():
            self.visual_window.lift()
            return
        prize = None
        selected_label = self.prize_var.get().strip()
        if selected_label:
            prize_id = selected_label.split(" - ", 1)[0]
            prize = next((item for item in self.prizes if item.prize_id == prize_id), None)
        if not prize:
            available = available_prizes(self.prizes, self.state)
            if not available:
                messagebox.showwarning("提示", "当前没有可抽奖项。")
                return
            prize = available[0]
        excluded_ids = self._current_excluded_ids()
        background_color = str(self.config.get("visual_background_color", "#0b0f1c"))
        background_path = self.config.get("visual_background") or None
        background_music_path = self.config.get("visual_music") or None
        win_sound_path = self.config.get("win_sound", "win.mp3") or None
        screen_geometry = {
            "x": int(self.config.get("visual_screen_x", 0) or 0),
            "y": int(self.config.get("visual_screen_y", 0) or 0),
            "width": int(self.config.get("visual_screen_width", 0) or 0),
            "height": int(self.config.get("visual_screen_height", 0) or 0),
        }
        self.visual_window = VisualLotteryWindow(
            self.root,
            self.base_dir,
            prize,
            self.prizes,
            self.people,
            self.state,
            self.global_must_win,
            excluded_ids,
            background_color,
            background_path,
            background_music_path,
            win_sound_path,
            screen_geometry,
            self._on_visual_complete,
            self._on_visual_closed,
        )

    def _on_visual_complete(self, winners: list[dict[str, Any]]) -> None:
        if winners:
            self._persist_state()
            self._refresh_prizes()
            self._refresh_winners()

    def _on_visual_closed(self) -> None:
        self.visual_window = None

    def _open_visual_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("大屏设置")
        dialog.transient(self.root)
        dialog.grab_set()

        background_color_var = tk.StringVar(value=str(self.config.get("visual_background_color", "#0b0f1c")))
        background_path_var = tk.StringVar(value=str(self.config.get("visual_background", "")))
        music_path_var = tk.StringVar(value=str(self.config.get("visual_music", "")))
        win_sound_var = tk.StringVar(value=str(self.config.get("win_sound", "win.mp3")))
        screen_x_var = tk.StringVar(value=str(self.config.get("visual_screen_x", 0)))
        screen_y_var = tk.StringVar(value=str(self.config.get("visual_screen_y", 0)))
        screen_width_var = tk.StringVar(value=str(self.config.get("visual_screen_width", 0)))
        screen_height_var = tk.StringVar(value=str(self.config.get("visual_screen_height", 0)))

        ttk.Label(dialog, text="背景颜色:").grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=background_color_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=6)

        def pick_color() -> None:
            color = colorchooser.askcolor(color=background_color_var.get(), parent=dialog)
            if color and color[1]:
                background_color_var.set(color[1])

        ttk.Button(dialog, text="选择颜色", command=pick_color).grid(row=0, column=2, padx=6)

        ttk.Label(dialog, text="背景图片:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=background_path_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=6)

        def pick_background() -> None:
            path = filedialog.askopenfilename(
                title="选择背景图片",
                filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp"), ("All files", "*.*")],
            )
            if path:
                background_path_var.set(self._relative_or_absolute(Path(path)))

        ttk.Button(dialog, text="选择文件", command=pick_background).grid(row=1, column=2, padx=6)

        ttk.Label(dialog, text="背景音乐:").grid(row=2, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=music_path_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=6)

        def pick_music() -> None:
            path = filedialog.askopenfilename(
                title="选择背景音乐",
                filetypes=[("Audio files", "*.mp3;*.wav;*.ogg"), ("All files", "*.*")],
            )
            if path:
                music_path_var.set(self._relative_or_absolute(Path(path)))

        ttk.Button(dialog, text="选择文件", command=pick_music).grid(row=2, column=2, padx=6)

        ttk.Label(dialog, text="中奖音乐:").grid(row=3, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=win_sound_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=6)

        def pick_win_sound() -> None:
            path = filedialog.askopenfilename(
                title="选择中奖音乐",
                filetypes=[("Audio files", "*.mp3;*.wav;*.ogg"), ("All files", "*.*")],
            )
            if path:
                win_sound_var.set(self._relative_or_absolute(Path(path)))

        ttk.Button(dialog, text="选择文件", command=pick_win_sound).grid(row=3, column=2, padx=6)

        ttk.Label(dialog, text="屏幕位置 X:").grid(row=4, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=screen_x_var, width=10).grid(row=4, column=1, sticky=tk.W, pady=6)
        ttk.Label(dialog, text="屏幕位置 Y:").grid(row=4, column=2, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(dialog, textvariable=screen_y_var, width=10).grid(row=4, column=3, sticky=tk.W, pady=6)

        ttk.Label(dialog, text="屏幕宽度:").grid(row=5, column=0, sticky=tk.W, padx=8, pady=6)
        ttk.Entry(dialog, textvariable=screen_width_var, width=10).grid(row=5, column=1, sticky=tk.W, pady=6)
        ttk.Label(dialog, text="屏幕高度:").grid(row=5, column=2, sticky=tk.W, padx=6, pady=6)
        ttk.Entry(dialog, textvariable=screen_height_var, width=10).grid(row=5, column=3, sticky=tk.W, pady=6)

        info_label = ttk.Label(dialog, text="设置保存后，下次开启大屏模式生效。")
        info_label.grid(row=6, column=0, columnspan=4, sticky=tk.W, padx=8, pady=6)

        def on_save() -> None:
            self.config["visual_background_color"] = background_color_var.get().strip() or "#0b0f1c"
            self.config["visual_background"] = background_path_var.get().strip()
            self.config["visual_music"] = music_path_var.get().strip()
            self.config["win_sound"] = win_sound_var.get().strip()
            try:
                self.config["visual_screen_x"] = int(screen_x_var.get() or 0)
                self.config["visual_screen_y"] = int(screen_y_var.get() or 0)
                self.config["visual_screen_width"] = int(screen_width_var.get() or 0)
                self.config["visual_screen_height"] = int(screen_height_var.get() or 0)
            except ValueError:
                messagebox.showerror("错误", "屏幕位置和尺寸必须为整数。", parent=dialog)
                return
            self._save_config_file()
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, padding=10)
        button_frame.grid(row=7, column=0, columnspan=4, sticky=tk.W)
        ttk.Button(button_frame, text="保存", command=on_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=6)

        dialog.wait_window()

    def _handle_space(self, event: tk.Event) -> None:
        current = time.monotonic()
        if current - self.last_space_time < 1.0:
            return
        self.last_space_time = current
        if self.draw_phase == "idle":
            self._enter_draw()
        elif self.draw_phase == "entered":
            self._start_spin()
        elif self.draw_phase == "spinning":
            self._draw_lucky()
        elif self.draw_phase == "drawn":
            self._transfer_draw()

    def _refresh_draw_prize_list(self) -> None:
        if not hasattr(self, "draw_prize_list"):
            return
        self.draw_prize_list.delete(0, tk.END)
        for prize in self.prizes:
            remaining = remaining_slots(prize, self.state)
            self.draw_prize_list.insert(tk.END, f"{prize.prize_id} {prize.name} ({remaining})")

    def _on_draw_prize_select(self, event: tk.Event) -> None:
        selection = self.draw_prize_list.curselection()
        if not selection:
            return
        index = selection[0]
        prize = self.prizes[index]
        self.draw_selected_prize_id = prize.prize_id
        remaining = remaining_slots(prize, self.state)
        self.draw_prize_info.config(text=f"当前奖项: {prize.name} 剩余 {remaining}")

    def _build_idle_grid(self) -> None:
        if not self.draw_canvas:
            return
        self.draw_canvas.delete("all")
        names = [person.name for person in self.people if person.person_id not in {w['person_id'] for w in self.state["winners"]}]
        if not names:
            names = [person.name for person in self.people]
        if not names:
            names = ["暂无人员"]
        width = self.draw_canvas.winfo_width() or 800
        height = self.draw_canvas.winfo_height() or 500
        cols = 10
        rows = 6
        needed = cols * rows
        pool = [names[i % len(names)] for i in range(needed)]
        self.draw_items = []
        cell_w = width / cols
        cell_h = height / rows
        for idx, name in enumerate(pool):
            col = idx % cols
            row = idx // cols
            x = col * cell_w + cell_w / 2
            y = row * cell_h + cell_h / 2
            item_id = self.draw_canvas.create_text(x, y, text=name, fill="#f2f2f2", font=("Helvetica", 12, "bold"))
            self.draw_items.append({"id": item_id, "vx": 1.5, "vy": 1.2})
        self.draw_phase = "idle"
        self._animate_idle_grid()

    def _animate_idle_grid(self) -> None:
        if not self.draw_canvas or self.draw_phase != "idle":
            return
        width = self.draw_canvas.winfo_width()
        height = self.draw_canvas.winfo_height()
        for item in self.draw_items:
            self.draw_canvas.move(item["id"], item["vx"], item["vy"])
            x, y = self.draw_canvas.coords(item["id"])
            if x < 20 or x > width - 20:
                item["vx"] *= -1
            if y < 20 or y > height - 20:
                item["vy"] *= -1
        self.draw_after_id = self.draw_canvas.after(50, self._animate_idle_grid)

    def _enter_draw(self) -> None:
        if not self.draw_canvas:
            return
        if not self.draw_selected_prize_id and self.prizes:
            self.draw_selected_prize_id = self.prizes[0].prize_id
        self.draw_canvas.delete("all")
        self.draw_phase = "entered"
        self.draw_speed = 0.01
        self.draw_angle = 0.0
        self._build_ball()
        self._animate_ball()

    def _build_ball(self) -> None:
        if not self.draw_canvas:
            return
        self.draw_canvas.delete("all")
        names = [person.name for person in self.people if person.person_id not in {w['person_id'] for w in self.state["winners"]}]
        if not names:
            names = [person.name for person in self.people]
        if not names:
            names = ["暂无人员"]
        count = max(40, len(names))
        pool = [names[i % len(names)] for i in range(count)]
        width = self.draw_canvas.winfo_width() or 800
        height = self.draw_canvas.winfo_height() or 500
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) * 0.35
        self.draw_items = []
        for idx, name in enumerate(pool):
            angle = (2 * 3.1416 / count) * idx
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            item_id = self.draw_canvas.create_text(x, y, text=name, fill="#ffd1e8", font=("Helvetica", 10, "bold"))
            self.draw_items.append({"id": item_id, "angle": angle, "radius": radius})

    def _animate_ball(self) -> None:
        if not self.draw_canvas or self.draw_phase not in {"entered", "spinning"}:
            return
        width = self.draw_canvas.winfo_width()
        height = self.draw_canvas.winfo_height()
        center_x = width / 2
        center_y = height / 2
        self.draw_angle += self.draw_speed
        for item in self.draw_items:
            angle = item["angle"] + self.draw_angle
            x = center_x + item["radius"] * math.cos(angle)
            y = center_y + item["radius"] * math.sin(angle)
            self.draw_canvas.coords(item["id"], x, y)
        self.draw_after_id = self.draw_canvas.after(40, self._animate_ball)

    def _start_spin(self) -> None:
        if self.draw_phase not in {"entered", "idle"}:
            return
        self.draw_phase = "spinning"
        self.draw_speed = 0.2
        self._animate_ball()

    def _draw_lucky(self) -> None:
        if self.draw_phase != "spinning":
            return
        self.draw_phase = "drawn"
        if not self.draw_selected_prize_id:
            messagebox.showwarning("提示", "请先选择奖项。")
            return
        prize = next((item for item in self.prizes if item.prize_id == self.draw_selected_prize_id), None)
        if not prize:
            messagebox.showerror("错误", "奖项不存在。")
            return
        excluded_ids = self._current_excluded_ids()
        preview_state = copy.deepcopy(self.state)
        self.pending_winners = draw_prize(prize, self.people, preview_state, self.global_must_win, excluded_ids)
        self.pending_state = preview_state
        if not self.pending_winners:
            messagebox.showinfo("结果", "本次未抽出新的中奖名单。")
            return
        names = "\n".join([f"{w['person_name']} ({w['person_id']})" for w in self.pending_winners])
        self._show_winner_popup(names)

    def _show_winner_popup(self, names: str) -> None:
        if not self.draw_canvas:
            return
        width = self.draw_canvas.winfo_width()
        height = self.draw_canvas.winfo_height()
        self.draw_canvas.delete("winner_popup")
        self.draw_canvas.create_rectangle(
            width * 0.3,
            height * 0.35,
            width * 0.7,
            height * 0.65,
            fill="#f7d6e5",
            outline="#ffffff",
            width=2,
            tags="winner_popup",
        )
        self.draw_canvas.create_text(
            width / 2,
            height / 2,
            text=names,
            fill="#2f1f33",
            font=("Helvetica", 14, "bold"),
            tags="winner_popup",
        )

    def _transfer_draw(self) -> None:
        if not self.pending_state or not self.pending_winners:
            messagebox.showinfo("提示", "暂无可转存的抽奖结果。")
            return
        self.state = self.pending_state
        self.pending_state = None
        self._persist_state()
        self._refresh_prizes()
        self._refresh_winners()
        self._refresh_draw_prize_list()
        self.pending_winners = []
        messagebox.showinfo("完成", "本次抽奖已转存。")

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

        excluded_ids = self._current_excluded_ids()
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
        excluded_ids = self._current_excluded_ids()
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
        self.admin_password = str(self.config.get("admin_password", ""))
        self.is_admin = False
        self.participants_file = resolve_path(self.base_dir, self.config["participants_file"])
        self.prizes_file = resolve_path(self.base_dir, self.config["prizes_file"])
        self.excluded_file = resolve_path(self.base_dir, self.config.get("excluded_file", "data/excluded.csv"))
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
        self.config_path_var.set(str(self.config_path))
        self._update_login_state()
        self._refresh_people_tree()
        self._refresh_prizes_tree()
        self._refresh_excluded_tree()
        self._refresh_prizes()
        self._refresh_winners()
        if self.visual_window and self.visual_window.winfo_exists():
            self.visual_window.update_prizes(self.prizes, self.state)
        if self.wheel_window and self.wheel_window.winfo_exists():
            self.wheel_window.update_prizes(self.prizes, self.state)
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

        is_admin = self.is_admin
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
        ttk.Checkbutton(dialog, text="排除已中奖", variable=exclude_previous_var).grid(
            row=3, column=0, columnspan=2, sticky=tk.W, padx=10
        )
        if is_admin:
            ttk.Label(dialog, text="保底工号(逗号分隔):").grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)
            ttk.Entry(dialog, textvariable=must_win_var).grid(row=4, column=1, padx=10, pady=5)
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
            if is_admin:
                must_win_ids = [item.strip() for item in must_win_var.get().split(",") if item.strip()]
                exclude_must_win = exclude_must_win_var.get()
                exclude_excluded = exclude_excluded_var.get()
            else:
                must_win_ids = [] if initial is None else list(initial.get("must_win_ids", []))
                exclude_must_win = True if initial is None else bool(initial.get("exclude_must_win", True))
                exclude_excluded = True if initial is None else bool(initial.get("exclude_excluded_list", True))
            nonlocal result
            result = {
                "id": prize_id,
                "name": name,
                "count": count,
                "exclude_previous_winners": exclude_previous_var.get(),
                "exclude_must_win": exclude_must_win,
                "exclude_excluded_list": exclude_excluded,
                "must_win_ids": must_win_ids,
            }
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        button_frame = ttk.Frame(dialog, padding=10)
        button_frame.grid(row=7 if is_admin else 5, column=0, columnspan=2)
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
        write_people_data(self.participants_file, self.people_data)
        self.people = parse_people_entries(self.people_data)
        messagebox.showinfo("成功", "人员名单已保存。")

    def _save_prizes(self) -> None:
        if not self._apply_prizes_change(self.prizes_data):
            return
        write_prizes_data(self.prizes_file, self.prizes_data)
        self.prizes = parse_prize_entries(self.prizes_data)
        self.global_must_win = build_global_must_win(self.prizes)
        self._refresh_prizes()
        if self.visual_window and self.visual_window.winfo_exists():
            self.visual_window.update_prizes(self.prizes, self.state)
        if self.wheel_window and self.wheel_window.winfo_exists():
            self.wheel_window.update_prizes(self.prizes, self.state)
        messagebox.showinfo("成功", "奖项配置已保存。")

    def _save_excluded(self) -> None:
        if not self._apply_excluded_change(self.excluded_data):
            return
        write_people_data(self.excluded_file, self.excluded_data)
        self.excluded_people = parse_people_entries(self.excluded_data)
        messagebox.showinfo("成功", "排查名单已保存。")

    def _import_people(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要导入的名单文件",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        path_obj = Path(path)
        try:
            data = read_people_data(path_obj)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("导入失败", f"无法读取 {path_obj}: {exc}")
            return
        try:
            parse_people_entries(data)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self._apply_people_change(data)

    def _export_people(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        write_people_data(Path(path), self.people_data)
        messagebox.showinfo("导出完成", f"已导出到 {path}")

    def _import_prizes(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要导入的奖项文件",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        path_obj = Path(path)
        try:
            data = read_prizes_data(path_obj)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("导入失败", f"无法读取 {path_obj}: {exc}")
            return
        try:
            parse_prize_entries(data)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self._apply_prizes_change(data)

    def _export_prizes(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        write_prizes_data(Path(path), self.prizes_data)
        messagebox.showinfo("导出完成", f"已导出到 {path}")

    def _import_excluded(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要导入的排查名单",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        path_obj = Path(path)
        try:
            data = read_people_data(path_obj)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("导入失败", f"无法读取 {path_obj}: {exc}")
            return
        try:
            parse_people_entries(data)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self._apply_excluded_change(data)

    def _export_excluded(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择导出位置",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json")],
        )
        if not path:
            return
        write_people_data(Path(path), self.excluded_data)
        messagebox.showinfo("导出完成", f"已导出到 {path}")


def main() -> None:
    config_path = Path("python/config.json")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    root = tk.Tk()
    app = LotteryApp(root, config_path)
    root.mainloop()


if __name__ == "__main__":
    main()
