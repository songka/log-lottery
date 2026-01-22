#!/usr/bin/env python3
"""UI layout and event binding for the wheel window."""

from __future__ import annotations

import ctypes
import importlib
import importlib.util
import sys
from ctypes import wintypes
import time
import tkinter as tk
from tkinter import simpledialog, ttk

from lottery import remaining_slots


class WheelWindowUI:
    def _build_ui(self) -> None:
        """Frame + Grid 布局"""
        self.main_container = tk.Frame(self, bg=self.colors["panel_bg"])
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # ================= 左侧面板 =================
        self.left_sidebar = tk.Frame(self.main_container, bg=self.colors["panel_bg"], width=320)
        self.left_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.left_sidebar.pack_propagate(False)

        # 标题区
        self.title_frame = tk.Frame(self.left_sidebar, bg=self.colors["panel_bg"], pady=30)
        self.title_frame.pack(fill=tk.X)
        self.title_label = tk.Label(
            self.title_frame,
            textvariable=self.title_text_var,
            font=("Microsoft YaHei UI", 18, "bold"),
            bg=self.colors["panel_bg"],
            fg=self.colors["title_fg"],
            wraplength=300,
        )
        self.title_label.pack()
        self.title_label.bind("<Double-Button-1>", self._edit_title)
        self.title_hint_label = tk.Label(
            self.title_frame,
            text="(双击修改标题)",
            font=("Arial", 8),
            bg=self.colors["panel_bg"],
            fg=self.colors["text_muted"],
        )
        self.title_hint_label.pack(pady=2)

        self.history_label = tk.Label(
            self.left_sidebar,
            text="🏆 荣耀榜单",
            font=("Microsoft YaHei UI", 14),
            bg=self.colors["panel_bg"],
            fg=self.colors["text_main"],
        )
        self.history_label.pack(pady=(10, 5))

        self.history_listbox = tk.Listbox(
            self.left_sidebar,
            bg=self.colors["history_bg"],
            fg=self.colors["history_fg"],
            font=("Microsoft YaHei UI", 12), 
            highlightthickness=0, 
            borderwidth=0,
            activestyle="none",
        )
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # ================= 右侧面板 =================
        self.right_sidebar = tk.Frame(self.main_container, bg=self.colors["panel_bg"], width=320)
        self.right_sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_sidebar.pack_propagate(False)

        # 结果提示
        self.status_frame = tk.Frame(self.right_sidebar, bg=self.colors["panel_bg"], pady=20)
        self.status_frame.pack(fill=tk.X)
        self.status_title_label = tk.Label(
            self.status_frame,
            text="开奖状态",
            bg=self.colors["panel_bg"],
            fg=self.colors["text_muted"],
            font=("Microsoft YaHei UI", 12),
        )
        self.status_title_label.pack(anchor=tk.W, padx=20)
        self.status_label = tk.Label(
            self.status_frame,
            textvariable=self.result_var,
            bg=self.colors["panel_bg"],
            fg=self.colors["status_fg"],
            font=("Microsoft YaHei UI", 16, "bold"),
            wraplength=300,
            justify=tk.LEFT,
        )
        self.status_label.pack(anchor=tk.W, pady=(5, 0))

        # 本轮名单
        self.winner_title_label = tk.Label(
            self.right_sidebar,
            text="🎉 本轮中奖",
            bg=self.colors["panel_bg"],
            fg=self.colors["status_fg"],
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.winner_title_label.pack(anchor=tk.W, padx=20, pady=(20, 5))
        
        self.list_frame = tk.Frame(self.right_sidebar, bg=self.colors["panel_border"], padx=1, pady=1)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        scrollbar = tk.Scrollbar(self.list_frame, orient="vertical", bg=self.colors["panel_bg"])
        self.winner_listbox = tk.Listbox(
            self.list_frame,
            bg=self.colors["winner_bg"],
            fg=self.colors["winner_fg"],
            font=("Microsoft YaHei UI", 13),
            highlightthickness=0,
            borderwidth=0,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.winner_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.winner_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 底部控制
        self.ctrl_frame = tk.Frame(self.right_sidebar, bg=self.colors["panel_bg"], padx=20, pady=30)
        self.ctrl_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.ctrl_title_label = tk.Label(
            self.ctrl_frame, text="选择奖项:", bg=self.colors["panel_bg"], fg=self.colors["text_muted"]
        )
        self.ctrl_title_label.pack(anchor=tk.W)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "TCombobox",
            fieldbackground=self.colors["combo_bg"],
            background=self.colors["combo_border"],
            foreground=self.colors["combo_fg"],
            arrowcolor=self.colors["combo_arrow"],
            font=("Microsoft YaHei UI", 12),
        )
        
        self.prize_combo = ttk.Combobox(
            self.ctrl_frame, textvariable=self.prize_var, state="readonly", font=("Microsoft YaHei UI", 12)
        )
        self.prize_combo.pack(fill=tk.X, pady=(2, 15), ipady=5)
        self.prize_combo.bind("<<ComboboxSelected>>", self._handle_prize_change)

        self.action_btn = tk.Button(
            self.ctrl_frame,
            text="按住蓄力 / 点击开始",
            bg=self.colors["gold"],
            fg="#5C1010",
            font=("Microsoft YaHei UI", 16, "bold"),
            relief="flat",
            cursor="hand2",
        )
        self.action_btn.pack(fill=tk.X, pady=(0, 10), ipady=10)
        self.action_btn.bind("<ButtonPress-1>", self._on_btn_down)
        self.action_btn.bind("<ButtonRelease-1>", self._on_btn_up)
        
        self.reset_btn = tk.Button(
            self.ctrl_frame,
            text="⟳ 重置名单 (清空队列)",
            command=self._prepare_wheel,
            bg=self.colors["panel_border"],
            fg=self.colors["text_main"],
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            cursor="hand2",
        )
        self.reset_btn.pack(fill=tk.X)

        # ================= 中间画布 =================
        self.canvas = tk.Canvas(self.main_container, bg=self.colors["bg_canvas"], highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 性能优化(Throttling)：窗口变化时仅请求限频重绘
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _edit_title(self, event):
        new_title = simpledialog.askstring("设置", "修改大屏标题：", initialvalue=self.title_text_var.get(), parent=self)
        if new_title:
            self.title_text_var.set(new_title)

    def _bind_controls(self):
        self.bind("<KeyPress-space>", self._on_key_down)
        self.bind("<KeyRelease-space>", self._on_key_up)
        self.bind("<F11>", self._toggle_fullscreen)
        self.focus_set()

    def _on_canvas_configure(self, event) -> None:
        """性能优化(Throttling)：窗口拖动/缩放时合并重绘请求。"""
        self._last_resize_event = time.monotonic()
        if self._pending_resize_render:
            return
        self._pending_resize_render = True

        def _run():
            self._pending_resize_render = False
            self._last_resize_render_time = time.monotonic()
            self._resize_render_after_id = None
            self._request_render(force=True)

        self._resize_render_after_id = self.after(33, _run)

    def _toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.normal_geometry = self.geometry()
            screen_x, screen_y, screen_w, screen_h = self._get_primary_screen_geometry()
            self.geometry(f"{screen_w}x{screen_h}+{screen_x}+{screen_y}")
            self.attributes("-fullscreen", True)
        else:
            self.attributes("-fullscreen", False)
            if self.normal_geometry:
                self.geometry(self.normal_geometry)
            else:
                self.geometry("1440x900")

    def _handle_close(self) -> None:
        if self.draw_after_id: self.after_cancel(self.draw_after_id)
        if self.render_after_id: self.after_cancel(self.render_after_id)
        if self._resize_render_after_id: self.after_cancel(self._resize_render_after_id)
        if self.scroll_after_id: self.after_cancel(self.scroll_after_id)
        if self.summary_scroll_after_id: self.after_cancel(self.summary_scroll_after_id)
        if hasattr(self, "_stop_music"):
            self._stop_music()
        self.destroy()
        if self.on_close: self.on_close()

    def _refresh_prize_options(self, hide_completed: bool = False) -> None:
        """
        刷新奖项下拉列表。
        :param hide_completed: 是否强制隐藏剩余0的奖项（仅初始化和手动切换时为 True）
        """
        options = []
        current_val = self.prize_var.get()
        current_id = current_val.split(" - ")[0] if current_val else None

        for prize in self.prizes:
            remaining = remaining_slots(prize, self.lottery_state)
            # 隐藏逻辑：只有在要求隐藏、名额为0，且【不是当前选中项】时才剔除
            if hide_completed and remaining <= 0 and prize.prize_id != current_id:
                continue
            
            options.append(f"{prize.prize_id} - {prize.name} (剩余 {remaining})")
            
        self.prize_combo["values"] = options
        
        # 初始选择逻辑
        if options and (not self.prize_var.get() or self.prize_var.get() not in options):
            self.prize_var.set(options[0])
            self._prepare_wheel()
        elif not options and self._all_prizes_complete():
            self.phase = "prize_summary"
            self.result_var.set("🎉 所有奖项已完成！点击确认查看总榜")
            self._update_btn_state()

    def _refresh_history_list(self) -> None:
        if not hasattr(self, "history_listbox"): return
        self.history_listbox.delete(0, tk.END)
        
        winners = self.lottery_state.get("winners", [])
        for w in reversed(winners):
            name = w.get('person_name', '未知')
            prize = w.get('prize_name', '奖品')
            self.history_listbox.insert(tk.END, f"🎗 {prize} - {name}")

    def _handle_prize_change(self, event: tk.Event) -> None:
        if self.phase in ["idle", "finished", "wait_for_manual"]:
             self.target_queue = [] 
             self._prepare_wheel()

    def _update_btn_state(self):
        if self.phase == "prize_summary":
            if self._has_next_prize():
                self.action_btn.config(text="确认并继续", bg=self.colors["gold"], fg="#5C1010", state="normal")
            else:
                self.action_btn.config(text="确认并查看总榜", bg=self.colors["gold"], fg="#5C1010", state="normal")
            self.prize_combo.config(state="readonly")
        elif self.phase == "announcing":
            self.action_btn.config(text="🎙️ 播报中...", bg=self.colors["red_deep"], fg=self.colors["white"], state="normal")
            self.prize_combo.config(state="disabled")
        elif self.phase in ["charging", "spinning", "braking", "auto_wait", "removing"]:
            self.action_btn.config(text="STOP (点击暂停)", bg=self.colors["red"], fg=self.colors["white"], state="normal")
            self.prize_combo.config(state="disabled") 
        elif self.phase == "wait_for_manual":
             remaining = self._current_prize_remaining()
             if remaining <= 0:
                 self.action_btn.config(text="该奖项已抽完", bg=self.colors["panel_border"], fg=self.colors["white"], state="disabled")
             else:
                 self.action_btn.config(text="继续 (长按蓄力)", bg=self.colors["panel_border"], fg=self.colors["white"], state="normal")
             self.prize_combo.config(state="readonly") 
        else:
            remaining = self._current_prize_remaining()
            if remaining <= 0:
                self.action_btn.config(text="该奖项已抽完", bg=self.colors["panel_border"], fg=self.colors["white"], state="disabled")
            else:
                self.action_btn.config(text="按住蓄力 / 点击开始", bg=self.colors["gold"], fg="#5C1010", state="normal")
            self.prize_combo.config(state="readonly")

        if self.phase in ["idle", "wait_for_manual", "prize_summary"]:
            self.reset_btn.pack(fill=tk.X, pady=0, before=self.action_btn)
        else:
            self.reset_btn.pack_forget()

    def _apply_color_theme(self) -> None:
        self.configure(bg=self.colors["panel_bg"])
        self.main_container.configure(bg=self.colors["panel_bg"])
        self.left_sidebar.configure(bg=self.colors["panel_bg"])
        self.right_sidebar.configure(bg=self.colors["panel_bg"])
        self.title_frame.configure(bg=self.colors["panel_bg"])
        self.title_label.configure(bg=self.colors["panel_bg"], fg=self.colors["title_fg"])
        self.title_hint_label.configure(bg=self.colors["panel_bg"], fg=self.colors["text_muted"])
        self.history_label.configure(bg=self.colors["panel_bg"], fg=self.colors["text_main"])
        self.history_listbox.configure(bg=self.colors["history_bg"], fg=self.colors["history_fg"])
        self.status_frame.configure(bg=self.colors["panel_bg"])
        self.status_title_label.configure(bg=self.colors["panel_bg"], fg=self.colors["text_muted"])
        self.status_label.configure(bg=self.colors["panel_bg"], fg=self.colors["status_fg"])
        self.winner_title_label.configure(bg=self.colors["panel_bg"], fg=self.colors["status_fg"])
        self.list_frame.configure(bg=self.colors["panel_border"])
        self.winner_listbox.configure(bg=self.colors["winner_bg"], fg=self.colors["winner_fg"])
        self.ctrl_frame.configure(bg=self.colors["panel_bg"])
        self.ctrl_title_label.configure(bg=self.colors["panel_bg"], fg=self.colors["text_muted"])
        self.reset_btn.configure(bg=self.colors["panel_border"], fg=self.colors["text_main"])
        self.canvas.configure(bg=self.colors["bg_canvas"])
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "TCombobox",
            fieldbackground=self.colors["combo_bg"],
            background=self.colors["combo_border"],
            foreground=self.colors["combo_fg"],
            arrowcolor=self.colors["combo_arrow"],
            font=("Microsoft YaHei UI", 12),
        )

    def _get_current_screen_geometry(self) -> tuple[int, int, int, int]:
        if importlib.util.find_spec("screeninfo"):
            screeninfo = importlib.import_module("screeninfo")
            monitors = screeninfo.get_monitors()
            root_x = self.winfo_rootx()
            root_y = self.winfo_rooty()
            width = max(1, self.winfo_width())
            height = max(1, self.winfo_height())
            center_x = root_x + width / 2
            center_y = root_y + height / 2
            for monitor in monitors:
                if (
                    monitor.x <= center_x < monitor.x + monitor.width
                    and monitor.y <= center_y < monitor.y + monitor.height
                ):
                    return monitor.x, monitor.y, monitor.width, monitor.height
            if monitors:
                monitor = monitors[0]
                return monitor.x, monitor.y, monitor.width, monitor.height
        elif sys.platform.startswith("win"):
            hwnd = self.winfo_id()
            monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
            if monitor:
                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    width = info.rcMonitor.right - info.rcMonitor.left
                    height = info.rcMonitor.bottom - info.rcMonitor.top
                    return info.rcMonitor.left, info.rcMonitor.top, width, height

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        screen_x = root_x - (root_x % screen_w)
        screen_y = root_y - (root_y % screen_h)
        return screen_x, screen_y, screen_w, screen_h

    def _get_primary_screen_geometry(self) -> tuple[int, int, int, int]:
        if importlib.util.find_spec("screeninfo"):
            screeninfo = importlib.import_module("screeninfo")
            monitors = screeninfo.get_monitors()
            for monitor in monitors:
                if getattr(monitor, "is_primary", False):
                    return monitor.x, monitor.y, monitor.width, monitor.height
            if monitors:
                monitor = monitors[0]
                return monitor.x, monitor.y, monitor.width, monitor.height
        elif sys.platform.startswith("win"):
            monitor = ctypes.windll.user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
            if monitor:
                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    width = info.rcMonitor.right - info.rcMonitor.left
                    height = info.rcMonitor.bottom - info.rcMonitor.top
                    return info.rcMonitor.left, info.rcMonitor.top, width, height
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        return 0, 0, screen_w, screen_h
