#!/usr/bin/env python3
"""
Wheel-based lottery window with auto-scaling text and remote control support.
优化版 v2：解决姓名显示不全、支持主窗口联动控制。
"""

from __future__ import annotations

import copy
import math
import random
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from lottery import draw_prize, remaining_slots


class WheelLotteryWindow(tk.Toplevel):
    """Lottery window that renders a full spinning wheel."""

    def __init__(
        self,
        root: tk.Tk,
        prizes: list[Any],
        people: list[Any],
        state: dict[str, Any],
        global_must_win: set[str],
        excluded_ids: set[str],
        on_transfer: Callable[[dict[str, Any], list[dict[str, Any]]], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(root)
        self.root = root
        self.prizes = prizes
        self.people = people
        self.state = state
        self.global_must_win = global_must_win
        self.excluded_ids = excluded_ids
        self.on_transfer = on_transfer
        self.on_close = on_close

        self.title("幸运大转盘")
        self.geometry("1280x800")
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.configure(bg="#1a1c29")

        self.prize_var = tk.StringVar()
        self.result_var = tk.StringVar(value="等待开始...")
        
        # 内部状态
        self.phase = "idle"
        self.wheel_rotation = 0.0
        self.current_speed = 0.0
        self.wheel_names: list[dict] = [] 
        self.segment_angle = 0.0
        
        # 抽奖队列
        self.pending_state: dict[str, Any] | None = None
        self.pending_winners: list[dict[str, Any]] = []
        self.target_queue: list[int] = []
        self.revealed_winners: list[str] = []
        
        # 动画控制
        self.last_time = 0.0
        self.pause_start_time = 0.0
        self.pause_duration = 2.0
        self.draw_after_id: str | None = None
        
        self.colors = ["#FF5E5B", "#00F5D4", "#FFE66D"] 

        self._build_ui()
        self._refresh_prize_options()
        self._animate()

    def _build_ui(self) -> None:
        """Create the layout."""
        header = tk.Frame(self, bg="#2b2d3e", height=60)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="✨ 幸运大转盘", font=("Microsoft YaHei UI", 18, "bold"), bg="#2b2d3e", fg="#ffffff").pack(side=tk.LEFT, padx=20, pady=10)
        tk.Label(header, text="当前奖项:", bg="#2b2d3e", fg="#bbbbbb", font=("Microsoft YaHei UI", 12)).pack(side=tk.LEFT, padx=(20, 5))
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground="#2b2d3e", background="#2b2d3e", foreground="#333", arrowcolor="white")
        
        self.prize_combo = ttk.Combobox(header, textvariable=self.prize_var, state="readonly", width=35, font=("Microsoft YaHei UI", 11))
        self.prize_combo.pack(side=tk.LEFT, pady=12)
        self.prize_combo.bind("<<ComboboxSelected>>", self._handle_prize_change)

        container = tk.Frame(self, bg="#1a1c29")
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg="#1a1c29", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.canvas.bind("<Configure>", lambda e: self._render_wheel())

        sidebar = tk.Frame(container, bg="#212332", width=300)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 0))
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="状态提示", bg="#212332", fg="#5ee1ff", font=("Microsoft YaHei UI", 12)).pack(anchor=tk.W, padx=20, pady=(20, 10))
        self.status_label = tk.Label(sidebar, textvariable=self.result_var, bg="#212332", fg="#ffe66d", font=("Microsoft YaHei UI", 14, "bold"), wraplength=260, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, padx=20, pady=(0, 20))

        tk.Label(sidebar, text="🎉 本轮中奖名单", bg="#212332", fg="#ff5e5b", font=("Microsoft YaHei UI", 12)).pack(anchor=tk.W, padx=20, pady=(10, 5))
        self.winner_listbox = tk.Listbox(sidebar, bg="#1a1c29", fg="white", font=("Microsoft YaHei UI", 12), highlightthickness=0, borderwidth=0, height=10)
        self.winner_listbox.pack(fill=tk.X, padx=20, pady=5)

        btn_frame = tk.Frame(sidebar, bg="#212332")
        btn_frame.pack(fill=tk.X, padx=20, pady=20, side=tk.BOTTOM)

        def create_btn(text, cmd, color="#5ee1ff"):
            btn = tk.Button(btn_frame, text=text, command=cmd, bg=color, fg="#000000", font=("Microsoft YaHei UI", 11, "bold"), relief="flat", activebackground="white", activeforeground="black", cursor="hand2")
            btn.pack(fill=tk.X, pady=8, ipady=5)
            return btn

        create_btn("1. 准备转盘", self._prepare_wheel, "#00f5d4")
        create_btn("2. 开始抽奖", self._start_draw_sequence, "#ffe66d")
        create_btn("3. 保存结果", self._transfer_draw, "#ff5e5b")

    def _handle_close(self) -> None:
        if self.draw_after_id:
            self.after_cancel(self.draw_after_id)
            self.draw_after_id = None
        self.destroy()
        if self.on_close:
            self.on_close()

    # --- 关键修改：联动控制接口 ---
    def select_prize_by_id(self, prize_id: str) -> None:
        """Called by main app to switch prize automatically."""
        # 只有在空闲状态才允许外部切换，防止打断抽奖
        if self.phase != "idle":
            return
            
        options = self.prize_combo["values"]
        target_option = next((opt for opt in options if opt.startswith(f"{prize_id} - ")), None)
        
        if target_option:
            self.prize_var.set(target_option)
            self._prepare_wheel() # 自动加载数据
    # ---------------------------

    def _refresh_prize_options(self) -> None:
        options = []
        for prize in self.prizes:
            remaining = remaining_slots(prize, self.state)
            options.append(f"{prize.prize_id} - {prize.name} (剩余 {remaining})")
        self.prize_combo["values"] = options
        # 如果当前没有选中或者选中的不在列表中，默认选第一个
        current = self.prize_var.get()
        if options and (not current or current not in options):
            self.prize_var.set(options[0])
            self._prepare_wheel()

    def update_prizes(self, prizes: list[Any], state: dict[str, Any]) -> None:
        self.prizes = prizes
        self.state = state
        # 记录当前选中的ID，尝试刷新后保持选中
        current_val = self.prize_var.get()
        current_id = current_val.split(" - ")[0] if current_val else None
        
        self._refresh_prize_options()
        
        if current_id:
            # 尝试找回之前的选项
            self.select_prize_by_id(current_id)

    def _handle_prize_change(self, event: tk.Event) -> None:
        self._prepare_wheel()

    def _prepare_wheel(self) -> None:
        if self.phase not in ["idle", "finished"]:
            return

        label = self.prize_var.get().strip()
        if not label:
            return

        prize_id = label.split(" - ", 1)[0]
        prize = next((p for p in self.prizes if p.prize_id == prize_id), None)
        if not prize:
            return

        excluded_must_win = self.global_must_win if prize.exclude_must_win else set()
        excluded_must_win = excluded_must_win - set(prize.must_win_ids)
        
        eligible = [
            p for p in self.people
            if (
                p.person_id not in self.excluded_ids
                and (not prize.exclude_previous_winners or p.person_id not in {w["person_id"] for w in self.state["winners"]})
                and p.person_id not in excluded_must_win
            )
        ]

        if not eligible:
            self.wheel_names = []
            self.result_var.set("该奖项无可用候选人")
            self.winner_listbox.delete(0, tk.END)
            self._render_wheel()
            return

        # 打乱顺序，让颜色更均匀
        random.shuffle(eligible)

        total = len(eligible)
        self.segment_angle = 360.0 / total
        self.wheel_names = []
        
        for i, person in enumerate(eligible):
            self.wheel_names.append({
                "index": i,
                "id": person.person_id,
                "name": person.name,
                "color": self.colors[i % 3],
                "angle_center": i * self.segment_angle + self.segment_angle / 2
            })

        self.phase = "idle"
        self.wheel_rotation = 0.0
        self.result_var.set(f"准备就绪！共 {total} 人参与")
        self.winner_listbox.delete(0, tk.END)
        self.revealed_winners = []
        self._render_wheel()

    def _start_draw_sequence(self) -> None:
        if self.phase != "idle" or not self.wheel_names:
            return

        prize_label = self.prize_var.get()
        if not prize_label:
            return
        prize_id = prize_label.split(" - ", 1)[0]
        prize = next((p for p in self.prizes if p.prize_id == prize_id), None)
        
        preview_state = copy.deepcopy(self.state)
        winners = draw_prize(
            prize,
            self.people,
            preview_state,
            self.global_must_win,
            self.excluded_ids,
        )

        if not winners:
            messagebox.showinfo("结果", "未能抽出中奖者。")
            return

        self.pending_state = preview_state
        self.pending_winners = winners
        self.target_queue = []

        for winner in winners:
            target_idx = next((item["index"] for item in self.wheel_names if item["id"] == winner["person_id"]), -1)
            if target_idx != -1:
                self.target_queue.append(target_idx)

        if not self.target_queue:
            messagebox.showerror("错误", "数据同步错误。")
            return

        self.phase = "spinning"
        self.current_speed = 0.0
        self.result_var.set("抽奖开始！")
        self.winner_listbox.delete(0, tk.END)
        self.last_time = time.monotonic()

    def _transfer_draw(self) -> None:
        if self.phase != "finished" or not self.pending_state:
            messagebox.showinfo("提示", "请先完成抽奖。")
            return
        
        if self.on_transfer:
            self.on_transfer(self.pending_state, self.pending_winners)
        
        self.pending_state = None
        self.result_var.set("结果已保存。")
        self.phase = "idle"

    def _animate(self) -> None:
        current_time = time.monotonic()
        dt = current_time - self.last_time
        self.last_time = current_time

        if self.phase == "spinning":
            if self.current_speed < 25.0:
                self.current_speed += 12.0 * dt
            else:
                self.current_speed = 25.0 
            
            if self.current_speed >= 25.0 and self.target_queue:
                self.phase = "braking"

        elif self.phase == "braking":
            if not self.target_queue:
                self.phase = "finished"
            else:
                target_idx = self.target_queue[0]
                target_center = self.wheel_names[target_idx]["angle_center"]
                desired_rotation = (90 - target_center) % 360
                current_mod = self.wheel_rotation % 360
                dist = (desired_rotation - current_mod) % 360
                
                if self.current_speed > 3.0:
                    self.current_speed -= 6.0 * dt
                else:
                    if dist < 10 or dist > 350:
                        diff = desired_rotation - current_mod
                        if diff > 180: diff -= 360
                        if diff < -180: diff += 360
                        
                        self.current_speed = diff * 5.0 * dt
                        if abs(diff) < 0.5 and abs(self.current_speed) < 0.5:
                            self.wheel_rotation = desired_rotation
                            self.current_speed = 0
                            self._handle_stop()
                    else:
                         self.current_speed = max(1.5, self.current_speed * 0.98)

        elif self.phase == "pause":
            if current_time - self.pause_start_time > self.pause_duration:
                if self.target_queue:
                    self.phase = "spinning"
                    self.result_var.set("继续抽取下一位...")
                else:
                    self.phase = "finished"
                    self.result_var.set("所有名额抽取完毕！")
                    self._show_fireworks()

        self.wheel_rotation = (self.wheel_rotation + self.current_speed) % 360
        self._render_wheel()
        self.draw_after_id = self.after(20, self._animate)

    def _handle_stop(self):
        if not self.target_queue:
            return
        idx = self.target_queue.pop(0)
        winner_data = self.wheel_names[idx]
        info = f"{winner_data['name']} ({winner_data['id']})"
        self.revealed_winners.append(info)
        self.winner_listbox.insert(tk.END, f"🏆 {info}")
        self.result_var.set(f"恭喜！{info}")
        
        if self.target_queue:
            self.phase = "pause"
            self.pause_start_time = time.monotonic()
        else:
            self.phase = "finished"
            self.result_var.set("抽奖完成！")
            self._show_fireworks()

    def _render_wheel(self) -> None:
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        cx, cy = width / 2, height / 2
        radius = min(cx, cy) - 20
        
        if not self.wheel_names:
            self.canvas.create_text(cx, cy, text="请先准备抽奖数据", fill="#555", font=("Microsoft YaHei UI", 20))
            return

        # 人数少于150才显示转盘上的小字，否则太乱
        show_small_text = len(self.wheel_names) <= 150
        
        for item in self.wheel_names:
            start = (item["angle_center"] - self.segment_angle/2 + self.wheel_rotation) % 360
            self.canvas.create_arc(
                cx - radius, cy - radius, cx + radius, cy + radius,
                start=start, extent=self.segment_angle,
                fill=item["color"], outline=item["color"], width=1
            )
            
            # 转盘上的小字（仅绘制前几个字）
            if show_small_text:
                mid_angle_rad = math.radians(start + self.segment_angle/2)
                tx = cx + (radius * 0.85) * math.cos(mid_angle_rad)
                ty = cy - (radius * 0.85) * math.sin(mid_angle_rad)
                short_name = item["name"][:4] # 只取前4个字
                self.canvas.create_text(tx, ty, text=short_name, font=("Arial", 8, "bold"), fill="#1a1c29")

        # 中心装饰
        self.canvas.create_oval(cx - 30, cy - 30, cx + 30, cy + 30, fill="#ffffff", outline="#ffe66d", width=3)
        self.canvas.create_text(cx, cy, text="LUCKY", font=("Arial", 10, "bold"))

        # 指针
        self.canvas.create_polygon(
            cx, cy - radius + 10 + 40,
            cx - 10, cy - radius + 10,
            cx + 10, cy - radius + 10,
            fill="#ff0000", outline="#ffffff", width=2
        )
        
        # --- 关键修改：动态计算大字号 ---
        current_angle_at_pointer = (90 - self.wheel_rotation) % 360
        pointer_index = int(current_angle_at_pointer // self.segment_angle) % len(self.wheel_names)
        current_item = self.wheel_names[pointer_index]
        
        display_text = current_item["name"]
        if self.current_speed > 10.0:
            display_text = "Rolling..."
        
        # 根据名字长度动态调整字号
        name_len = len(display_text)
        if name_len < 4:
            font_size = 48
        elif name_len < 8:
            font_size = 36
        elif name_len < 12:
            font_size = 28
        else:
            font_size = 20 # 超长名字用小字号
            
        self.canvas.create_text(
            cx, cy - radius - 50, 
            text=display_text, 
            fill="#ffe66d", 
            font=("Microsoft YaHei UI", font_size, "bold")
        )
        # ---------------------------

    def _show_fireworks(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        for _ in range(25):
            x = random.randint(50, width-50)
            y = random.randint(50, height-50)
            color = random.choice(self.colors)
            size = random.randint(5, 15)
            self.canvas.create_oval(x, y, x+size, y+size, fill=color, tags="firework")
        self.root.after(500, lambda: self.canvas.delete("firework"))