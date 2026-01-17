#!/usr/bin/env python3
"""Wheel-based lottery window with suspenseful stopping."""

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
    """Lottery window that renders a spinning wheel and sequential stops."""

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

        self.title("转盘抽奖")
        self.geometry("1200x760")
        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        self.prize_var = tk.StringVar()
        self.result_var = tk.StringVar(value="等待抽奖...")
        self.phase = "idle"
        self.wheel_angle = 0.0
        self.wheel_speed = 0.0
        self.highlight_blocks: list[dict[str, float]] = []
        self.segment_names: list[str] = []
        self.segment_colors: list[str] = []
        self.segment_count = 0
        self.segment_angle = 0.0
        self.pending_state: dict[str, Any] | None = None
        self.pending_winners: list[dict[str, Any]] = []
        self.revealed_names: list[str] = []
        self.stop_index = 0
        self.stop_start = 0.0
        self.stop_durations: list[float] = []
        self.stop_sequence_start = 0.0
        self.draw_after_id: str | None = None

        self._build_ui()
        self._refresh_prize_options()
        self._animate()

    def _build_ui(self) -> None:
        """Create the wheel layout with control panel and canvas."""
        header = ttk.Frame(self, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text="转盘抽奖", font=("Helvetica", 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="当前奖项:").pack(side=tk.LEFT, padx=(12, 4))
        self.prize_combo = ttk.Combobox(header, textvariable=self.prize_var, state="readonly", width=30)
        self.prize_combo.pack(side=tk.LEFT)
        self.prize_combo.bind("<<ComboboxSelected>>", self._handle_prize_change)

        result_frame = ttk.Frame(self, padding=(10, 0, 10, 6))
        result_frame.pack(fill=tk.X)
        ttk.Label(result_frame, textvariable=self.result_var, foreground="#ffe66d", font=("Helvetica", 14, "bold")).pack(
            anchor=tk.W
        )

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg="#121423", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        control = ttk.Frame(container, width=240, padding=10)
        control.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(control, text="控制面板", font=("Helvetica", 12, "bold")).pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(control, text="准备抽奖", command=self._prepare_wheel).pack(fill=tk.X, pady=4)
        ttk.Button(control, text="开始抽奖", command=self._start_spin).pack(fill=tk.X, pady=4)
        ttk.Button(control, text="抽取幸运儿", command=self._draw_lucky).pack(fill=tk.X, pady=4)
        ttk.Button(control, text="转存该次抽奖", command=self._transfer_draw).pack(fill=tk.X, pady=4)
        ttk.Label(control, text="提示：先准备，再开始旋转", foreground="#888").pack(anchor=tk.W, pady=(12, 0))

    def _handle_close(self) -> None:
        if self.draw_after_id:
            self.after_cancel(self.draw_after_id)
            self.draw_after_id = None
        self.destroy()
        if self.on_close:
            self.on_close()

    def _refresh_prize_options(self) -> None:
        options = []
        for prize in self.prizes:
            remaining = remaining_slots(prize, self.state)
            options.append(f"{prize.prize_id} - {prize.name} (剩余 {remaining})")
        self.prize_combo["values"] = options
        if options:
            if self.prize_var.get() not in options:
                self.prize_var.set(options[0])
        else:
            self.prize_var.set("")

    def update_prizes(self, prizes: list[Any], state: dict[str, Any]) -> None:
        """Sync prize list with the main application."""
        self.prizes = prizes
        self.state = state
        self._refresh_prize_options()

    def _handle_prize_change(self, event: tk.Event) -> None:
        # When prize changes, reset the wheel to prepare again.
        self.phase = "idle"
        self.result_var.set("等待抽奖...")
        self._prepare_wheel()

    def _eligible_names(self, prize: Any) -> list[str]:
        """Build eligible names for the selected prize."""
        excluded_must_win = self.global_must_win if prize.exclude_must_win else set()
        excluded_must_win = excluded_must_win - set(prize.must_win_ids)
        return [
            person.name
            for person in self.people
            if (
                person.person_id not in self.excluded_ids
                and (not prize.exclude_previous_winners or person.person_id not in {w["person_id"] for w in self.state["winners"]})
                and person.person_id not in excluded_must_win
            )
        ]

    def _prepare_wheel(self) -> None:
        """Randomize the names on the wheel and reset animation state."""
        if not self.prize_var.get().strip():
            messagebox.showwarning("提示", "当前没有可抽奖项。")
            return
        prize = self._selected_prize()
        if not prize:
            return
        names = self._eligible_names(prize)
        if not names:
            names = [person.name for person in self.people] or ["暂无人员"]
        random.shuffle(names)

        # Use a bounded number of segments to keep text readable.
        self.segment_count = min(24, max(12, len(names)))
        self.segment_names = [names[i % len(names)] for i in range(self.segment_count)]
        self.segment_colors = self._build_segment_colors(self.segment_count)
        self.segment_angle = 360 / self.segment_count
        self.wheel_angle = 0.0
        self.wheel_speed = 0.0
        self.highlight_blocks = []
        self.pending_winners = []
        self.pending_state = None
        self.revealed_names = []
        self.result_var.set("准备完成，请开始抽奖")
        self.phase = "ready"
        self._render_wheel()

    def _build_segment_colors(self, count: int) -> list[str]:
        palette = ["#ff5e5b", "#ffe66d", "#00f5d4", "#9b5de5", "#f15bb5", "#5ee1ff"]
        colors = [palette[i % len(palette)] for i in range(count)]
        random.shuffle(colors)
        return colors

    def _start_spin(self) -> None:
        if self.phase not in {"ready", "idle"}:
            return
        if self.segment_count == 0:
            self._prepare_wheel()
            if self.segment_count == 0:
                return
        prize = self._selected_prize()
        if not prize:
            return
        draw_count = remaining_slots(prize, self.state)
        if draw_count <= 0:
            messagebox.showwarning("提示", "该奖项已抽完，请选择其他奖项。")
            return
        draw_count = min(draw_count, max(1, self.segment_count))
        self.highlight_blocks = []
        # Each highlight block rotates at its own speed to create layered motion.
        for index in range(draw_count):
            self.highlight_blocks.append(
                {
                    "angle": random.uniform(0, 360),
                    "speed": random.uniform(2.5, 4.5) + index * 0.4,
                    "base_speed": 0.0,
                    "stopped": False,
                }
            )
        for block in self.highlight_blocks:
            block["base_speed"] = block["speed"]
        self.wheel_speed = 6.5
        self.phase = "spinning"
        self.result_var.set("正在旋转...")

    def _draw_lucky(self) -> None:
        if self.phase != "spinning":
            return
        prize = self._selected_prize()
        if not prize:
            return
        preview_state = copy.deepcopy(self.state)
        self.pending_winners = draw_prize(
            prize,
            self.people,
            preview_state,
            self.global_must_win,
            self.excluded_ids,
        )
        self.pending_state = preview_state
        if not self.pending_winners:
            messagebox.showinfo("结果", "本次未抽出新的中奖名单。")
            return
        # Align highlight blocks with actual winners count for sequential stops.
        if len(self.pending_winners) < len(self.highlight_blocks):
            self.highlight_blocks = self.highlight_blocks[: len(self.pending_winners)]
        # Prepare sequential stop durations so each block stops at a different time.
        self.stop_durations = [random.uniform(1.4, 2.0) + index * 0.6 for index in range(len(self.pending_winners))]
        self.stop_index = 0
        self.stop_start = time.monotonic()
        self.stop_sequence_start = self.stop_start
        self.revealed_names = []
        self.phase = "stopping"
        self.result_var.set("即将揭晓幸运儿...")

    def _transfer_draw(self) -> None:
        if not self.pending_state or not self.pending_winners:
            messagebox.showinfo("提示", "暂无可转存的抽奖结果。")
            return
        if self.on_transfer:
            self.on_transfer(self.pending_state, self.pending_winners)
        self.pending_state = None
        self.pending_winners = []
        self.revealed_names = []
        self.result_var.set("已转存本次抽奖结果")
        self.phase = "idle"

    def _selected_prize(self) -> Any | None:
        label = self.prize_var.get().strip()
        if not label:
            return None
        prize_id = label.split(" - ", 1)[0]
        return next((item for item in self.prizes if item.prize_id == prize_id), None)

    def _animate(self) -> None:
        if self.phase in {"spinning", "stopping"}:
            self._update_spin()
        self.draw_after_id = self.after(40, self._animate)

    def _update_spin(self) -> None:
        # Update wheel rotation and per-block highlights each frame.
        self.wheel_angle = (self.wheel_angle + self.wheel_speed) % 360
        for block in self.highlight_blocks:
            block["angle"] = (block["angle"] + block["speed"]) % 360
        if self.phase == "stopping":
            self._update_stopping()
        self._render_wheel()

    def _update_stopping(self) -> None:
        if self.stop_index >= len(self.pending_winners):
            self.wheel_speed = 0.0
            self.phase = "stopped"
            self.result_var.set("抽奖完成，可转存结果")
            return
        now = time.monotonic()
        total_duration = sum(self.stop_durations)
        overall_progress = min(1.0, (now - self.stop_sequence_start) / total_duration)
        self.wheel_speed = max(0.4, 6.5 * ((1 - overall_progress) ** 2))

        current_block = self.highlight_blocks[self.stop_index]
        duration = self.stop_durations[self.stop_index]
        progress = min(1.0, (now - self.stop_start) / duration)
        current_block["speed"] = current_block["base_speed"] * ((1 - progress) ** 2)
        if progress >= 1:
            current_block["speed"] = 0.0
            current_block["stopped"] = True
            winner = self.pending_winners[self.stop_index]
            self.revealed_names.append(f"{winner['person_name']} ({winner['person_id']})")
            self.result_var.set("已抽中: " + "、".join(self.revealed_names))
            self.stop_index += 1
            self.stop_start = now

    def _render_wheel(self) -> None:
        if self.segment_count == 0:
            return
        self.canvas.delete("wheel")
        width = self.canvas.winfo_width() or 900
        height = self.canvas.winfo_height() or 600
        radius = min(width, height) * 0.42
        center_x = width / 2
        center_y = height / 2

        # Determine which segments should be highlighted based on moving blocks.
        active_indices = set()
        for block in self.highlight_blocks:
            angle = (block["angle"] - self.wheel_angle) % 360
            index = int(angle // self.segment_angle)
            active_indices.add(index)

        font_size = 14 if self.segment_count <= 12 else 12 if self.segment_count <= 18 else 10
        for index in range(self.segment_count):
            start_angle = self.wheel_angle + index * self.segment_angle
            color = self.segment_colors[index]
            if index in active_indices:
                # Brighten active blocks to signal the draw count.
                color = self._brighten(color, 0.25)
            self.canvas.create_arc(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                start=start_angle,
                extent=self.segment_angle,
                fill=color,
                outline="#121423",
                tags="wheel",
            )
            text_angle = math.radians(start_angle + self.segment_angle / 2)
            text_radius = radius * 0.72
            text_x = center_x + text_radius * math.cos(text_angle)
            text_y = center_y + text_radius * math.sin(text_angle)
            name = self.segment_names[index]
            # Trim long names to avoid collisions.
            display_name = name if len(name) <= 6 else f"{name[:6]}…"
            self.canvas.create_text(
                text_x,
                text_y,
                text=display_name,
                fill="#1b1428",
                font=("Helvetica", font_size, "bold"),
                tags="wheel",
            )

        # Draw a pointer to indicate the selection zone.
        pointer_size = 16
        self.canvas.create_polygon(
            center_x,
            center_y - radius - 8,
            center_x - pointer_size,
            center_y - radius - 32,
            center_x + pointer_size,
            center_y - radius - 32,
            fill="#ffe66d",
            outline="",
            tags="wheel",
        )

    def _brighten(self, color: str, factor: float) -> str:
        color = color.lstrip("#")
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
