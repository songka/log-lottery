#!/usr/bin/env python3
"""Visual big-screen lottery window."""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

import pygame
from PIL import Image, ImageTk

from lottery import draw_prize, remaining_slots, resolve_path


class VisualLotteryWindow(tk.Toplevel):
    """Big-screen visual lottery view with animated states."""

    BOUNCE = "bounce"
    SPHERE_SLOW = "sphere_slow"
    SPHERE_FAST = "sphere_fast"
    SPHERE_SLOWDOWN = "sphere_slowdown"
    TRANSITION = "transition"
    RESULT = "result"

    def __init__(
        self,
        root: tk.Tk,
        base_dir: Path,
        prize: Any,
        prizes: list[Any],
        people: list[Any],
        state: dict[str, Any],
        global_must_win: set[str],
        excluded_ids: set[str],
        include_excluded: bool,
        excluded_winner_range: tuple[int | None, int | None] | None,
        background_color: str,
        background_path: str | None,
        background_music_path: str | None,
        win_sound_path: str | None,
        screen_geometry: dict[str, int] | None,
        on_complete: Callable[[list[dict[str, Any]]], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(root)
        self.root = root
        self.base_dir = base_dir
        self.prize = prize
        self.prizes = prizes
        self.people = people
        self.state = state
        self.global_must_win = global_must_win
        self.excluded_ids = excluded_ids
        self.include_excluded = include_excluded
        self.excluded_winner_range = excluded_winner_range
        self.background_color = background_color or "#0b0f1c"
        self.background_path = background_path
        self.background_music_path = background_music_path
        self.win_sound_path = win_sound_path
        self.screen_geometry = screen_geometry
        self.on_complete = on_complete
        self.on_close = on_close

        self.title("视觉大屏模式")
        # Default geometry follows the configured screen placement for easy display control.
        if self.screen_geometry:
            width = self.screen_geometry.get("width")
            height = self.screen_geometry.get("height")
            x = self.screen_geometry.get("x", 0)
            y = self.screen_geometry.get("y", 0)
            if width and height:
                self.geometry(f"{width}x{height}+{x}+{y}")
            else:
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                width = int(screen_w * 0.9)
                height = int(screen_h * 0.9)
                self.geometry(f"{width}x{height}+{x}+{y}")
        self.fullscreen = False
        self.resizable(True, True)
        self.attributes("-fullscreen", self.fullscreen)
        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.bind("<Escape>", self._handle_escape)
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<space>", self._handle_space)

        self.control_bar = ttk.Frame(self, padding=8)
        self.control_bar.pack(fill=tk.X)
        ttk.Label(self.control_bar, text="当前奖项:").pack(side=tk.LEFT)
        self.prize_var = tk.StringVar(value=self._format_prize_label(self.prize))
        self.prize_combo = ttk.Combobox(self.control_bar, textvariable=self.prize_var, state="readonly", width=32)
        self.prize_combo.pack(side=tk.LEFT, padx=6)
        self.prize_combo.bind("<<ComboboxSelected>>", self._handle_prize_change)
        ttk.Label(self.control_bar, text="空格切换流程 (间隔>=1秒)").pack(side=tk.LEFT, padx=12)
        ttk.Label(self.control_bar, text="拖动此栏可移动窗口 · F11全屏", foreground="#5ee1ff").pack(
            side=tk.RIGHT
        )
        # Enable drag to move the window to an extended display.
        self.control_bar.bind("<ButtonPress-1>", self._start_drag)
        self.control_bar.bind("<B1-Motion>", self._on_drag)
        self.control_bar.bind("<ButtonRelease-1>", self._end_drag)

        self.canvas = tk.Canvas(self, bg=self.background_color, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._handle_resize)

        self.background_image = None
        self.background_original = None
        self.background_id = None

        self.drawn_ids = {winner["person_id"] for winner in self.state["winners"]}
        self.last_space_time = 0.0
        self.state_mode = self.BOUNCE
        self.items: list[dict[str, Any]] = []
        self.sphere_points: list[dict[str, Any]] = []
        self.after_id = None
        self.rotation_speed = 0.01
        self.rotation_angle = 0.0
        self.rotation_angle_y = 0.0
        self.projection_distance = 800.0
        self.base_font_size = 14
        self.particles: list[dict[str, Any]] = []
        self.ambient_particles: list[dict[str, Any]] = []
        self.ambient_rings: list[dict[str, Any]] = []
        self.transition_start = 0.0
        self.transition_duration = 1.2
        self.transition_items: list[int] = []
        self.drag_offset: tuple[int, int] | None = None
        self.slowdown_start = 0.0
        self.slowdown_duration = 2.4
        self.slowdown_initial_speed = 0.0
        self.normal_geometry = ""
        self.fullscreen_geometry = ""
        self.audio_ready = False
        self.win_sound = None
        self.music_ready = False

        self._refresh_prize_options()
        self._load_background()
        self._build_ambient_layer()
        self._init_audio()
        self._build_bounce_items()
        self._animate()

    def _handle_close(self) -> None:
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        if self.music_ready:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
        self.destroy()
        if self.on_close:
            self.on_close()

    def _handle_escape(self, event: tk.Event) -> None:
        if self.fullscreen:
            self._toggle_fullscreen(event)
            return
        self._handle_close()

    def _toggle_fullscreen(self, event: tk.Event | None = None) -> None:
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.normal_geometry = self.geometry()
            if self.screen_geometry:
                width = self.screen_geometry.get("width")
                height = self.screen_geometry.get("height")
                x = self.screen_geometry.get("x", 0)
                y = self.screen_geometry.get("y", 0)
                if width and height:
                    self.fullscreen_geometry = f"{width}x{height}+{x}+{y}"
            if not self.fullscreen_geometry:
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                self.fullscreen_geometry = f"{screen_w}x{screen_h}+0+0"
            self.geometry(self.fullscreen_geometry)
        else:
            if self.normal_geometry:
                self.geometry(self.normal_geometry)

    def _start_drag(self, event: tk.Event) -> None:
        if self.fullscreen:
            self._toggle_fullscreen()
        self.drag_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _on_drag(self, event: tk.Event) -> None:
        if not self.drag_offset:
            return
        offset_x, offset_y = self.drag_offset
        new_x = event.x_root - offset_x
        new_y = event.y_root - offset_y
        self.geometry(f"+{new_x}+{new_y}")

    def _end_drag(self, event: tk.Event) -> None:
        self.drag_offset = None

    def _handle_space(self, event: tk.Event) -> None:
        current = time.monotonic()
        if current - self.last_space_time < 1.0:
            return
        self.last_space_time = current
        if self.state_mode == self.BOUNCE:
            self.state_mode = self.SPHERE_SLOW
            self.rotation_speed = 0.01
            self._build_sphere()
        elif self.state_mode == self.SPHERE_SLOW:
            self.state_mode = self.SPHERE_FAST
            self.rotation_speed = 0.08
        elif self.state_mode == self.SPHERE_FAST:
            self._start_slowdown()

    def _handle_resize(self, event: tk.Event) -> None:
        self._load_background()
        self._build_ambient_layer()

    def _load_background(self) -> None:
        self.canvas.configure(bg=self.background_color)
        if not self.background_path:
            return
        path = resolve_path(self.base_dir, self.background_path)
        if not path.exists():
            return
        if self.background_original is None:
            self.background_original = Image.open(path)
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return
        resized = self.background_original.resize((width, height), Image.Resampling.LANCZOS)
        self.background_image = ImageTk.PhotoImage(resized)
        if self.background_id is None:
            self.background_id = self.canvas.create_image(0, 0, image=self.background_image, anchor=tk.NW)
            self.canvas.tag_lower(self.background_id)
        else:
            self.canvas.itemconfigure(self.background_id, image=self.background_image)

    def _init_audio(self) -> None:
        if not self.win_sound_path and not self.background_music_path:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if self.win_sound_path:
                path = resolve_path(self.base_dir, self.win_sound_path)
            else:
                path = None
            if path and path.exists():
                self.win_sound = pygame.mixer.Sound(str(path))
                self.audio_ready = True
            if self.background_music_path:
                music_path = resolve_path(self.base_dir, self.background_music_path)
                if music_path.exists():
                    pygame.mixer.music.load(str(music_path))
                    pygame.mixer.music.play(-1)
                    self.music_ready = True
        except pygame.error:
            self.audio_ready = False
            self.music_ready = False

    def _build_bounce_items(self) -> None:
        self.canvas.delete("visual_item")
        self.canvas.delete("result")
        self.canvas.delete("particle")
        if self.background_id is not None:
            self.canvas.tag_lower(self.background_id)
        names = self._build_display_names()
        if not names:
            names = ["暂无人员"]
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        self.items = []
        palette = ["#ff5e5b", "#ffe66d", "#00f5d4", "#9b5de5", "#f15bb5", "#5ee1ff"]
        for name in names[:80]:
            x = random.uniform(80, width - 80)
            y = random.uniform(80, height - 80)
            color = random.choice(palette)
            glow_id = self.canvas.create_text(
                x,
                y + 2,
                text=name,
                fill=color,
                font=("Helvetica", 22, "bold"),
                tags="visual_item",
            )
            item_id = self.canvas.create_text(
                x,
                y,
                text=name,
                fill="#fefcff",
                font=("Helvetica", 16, "bold"),
                tags="visual_item",
            )
            tag = f"bubble_{item_id}"
            self.canvas.addtag_withtag(tag, glow_id)
            self.canvas.addtag_withtag(tag, item_id)
            self.items.append(
                {
                    "id": item_id,
                    "tag": tag,
                    "vx": random.uniform(-3.5, 3.5),
                    "vy": random.uniform(-2.8, 2.8),
                }
            )

    def _build_sphere(self) -> None:
        self.canvas.delete("visual_item")
        self.canvas.delete("result")
        self.canvas.delete("particle")
        if self.background_id is not None:
            self.canvas.tag_lower(self.background_id)
        names = self._build_display_names()
        if not names:
            names = ["暂无人员"]
        if len(names) < 80:
            repeat_times = (80 // len(names)) + 1
            names = (names * repeat_times)[:80]
        count = len(names)
        radius = min(self.canvas.winfo_width() or 1200, self.canvas.winfo_height() or 700) * 0.35
        self.projection_distance = radius * 3.0
        self.sphere_points = []
        for index, name in enumerate(names):
            offset = 2 / count
            y = index * offset - 1 + offset / 2
            r = math.sqrt(1 - y * y)
            phi = index * math.pi * (3 - math.sqrt(5))
            x = math.cos(phi) * r
            z = math.sin(phi) * r
            item_id = self.canvas.create_text(
                0,
                0,
                text=name,
                fill="#80f7ff",
                font=("Helvetica", 12, "bold"),
                tags="visual_item",
            )
            self.sphere_points.append(
                {
                    "id": item_id,
                    "x": x * radius,
                    "y": y * radius,
                    "z": z * radius,
                }
            )

    def _animate(self) -> None:
        self._animate_ambient()
        if self.state_mode == self.BOUNCE:
            self._animate_bounce()
        elif self.state_mode in {self.SPHERE_SLOW, self.SPHERE_FAST}:
            self._animate_sphere()
        elif self.state_mode == self.SPHERE_SLOWDOWN:
            self._animate_slowdown()
        elif self.state_mode == self.TRANSITION:
            self._animate_transition()
        elif self.state_mode == self.RESULT:
            self._animate_particles()
        self.after_id = self.after(40, self._animate)

    def _animate_bounce(self) -> None:
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        for item in self.items:
            self.canvas.move(item["tag"], item["vx"], item["vy"])
            x, y = self.canvas.coords(item["id"])
            if x < 40 or x > width - 40:
                item["vx"] *= -1
            if y < 40 or y > height - 40:
                item["vy"] *= -1

    def _animate_sphere(self) -> None:
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        center_x = width / 2
        center_y = height / 2
        self.rotation_angle += self.rotation_speed
        self.rotation_angle_y += self.rotation_speed * 0.6
        cos_x = math.cos(self.rotation_angle)
        sin_x = math.sin(self.rotation_angle)
        cos_y = math.cos(self.rotation_angle_y)
        sin_y = math.sin(self.rotation_angle_y)
        for point in self.sphere_points:
            y = point["y"] * cos_x - point["z"] * sin_x
            z = point["y"] * sin_x + point["z"] * cos_x
            x = point["x"] * cos_y - z * sin_y
            z = point["x"] * sin_y + z * cos_y
            factor = self.projection_distance / (self.projection_distance - z)
            screen_x = center_x + x * factor
            screen_y = center_y + y * factor
            size = max(8, int(self.base_font_size * factor))
            color_value = int(160 + 95 * min(1.0, factor - 0.4))
            color_value = max(120, min(255, color_value))
            color = f"#{color_value:02x}{min(255, color_value + 10):02x}ff"
            self.canvas.coords(point["id"], screen_x, screen_y)
            self.canvas.itemconfigure(point["id"], font=("Helvetica", size, "bold"), fill=color)

    def _start_slowdown(self) -> None:
        # Slow down the sphere to build suspense before revealing winners.
        self.state_mode = self.SPHERE_SLOWDOWN
        self.slowdown_start = time.monotonic()
        self.slowdown_initial_speed = max(self.rotation_speed, 0.02)

    def _animate_slowdown(self) -> None:
        progress = (time.monotonic() - self.slowdown_start) / self.slowdown_duration
        eased = max(0.0, 1.0 - progress)
        self.rotation_speed = max(0.002, self.slowdown_initial_speed * (eased**2))
        self._animate_sphere()
        if progress >= 1:
            self.rotation_speed = 0.0
            self._start_transition()

    def _start_transition(self) -> None:
        self.state_mode = self.TRANSITION
        self.transition_start = time.monotonic()
        self.canvas.delete("transition")
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        center_x = width / 2
        center_y = height / 2
        pulse = self.canvas.create_oval(
            center_x - 40,
            center_y - 40,
            center_x + 40,
            center_y + 40,
            outline="#5ee1ff",
            width=3,
            tags="transition",
        )
        burst = self.canvas.create_oval(
            center_x - 80,
            center_y - 80,
            center_x + 80,
            center_y + 80,
            outline="#ff5e5b",
            width=4,
            tags="transition",
        )
        headline = self.canvas.create_text(
            center_x,
            center_y,
            text="锁定幸运之星",
            fill="#ffe66d",
            font=("Helvetica", 32, "bold"),
            tags="transition",
        )
        self.transition_items = [pulse, burst, headline]

    def _animate_transition(self) -> None:
        progress = (time.monotonic() - self.transition_start) / self.transition_duration
        if progress >= 1:
            self.canvas.delete("transition")
            self.state_mode = self.RESULT
            self._draw_results()
            return
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        center_x = width / 2
        center_y = height / 2
        pulse, burst, headline = self.transition_items
        pulse_radius = 40 + progress * 220
        burst_radius = 80 + progress * 320
        self.canvas.coords(
            pulse,
            center_x - pulse_radius,
            center_y - pulse_radius,
            center_x + pulse_radius,
            center_y + pulse_radius,
        )
        self.canvas.coords(
            burst,
            center_x - burst_radius,
            center_y - burst_radius,
            center_x + burst_radius,
            center_y + burst_radius,
        )
        glow_color = "#%02x%02x%02x" % (255, int(120 + 100 * progress), 120)
        self.canvas.itemconfigure(pulse, outline=glow_color)
        self.canvas.itemconfigure(burst, outline="#5ee1ff")
        self.canvas.itemconfigure(
            headline, font=("Helvetica", int(32 + progress * 12), "bold"), fill="#ffe66d"
        )

    def _draw_results(self) -> None:
        if not self.prize:
            return
        try:
            winners = draw_prize(
                self.prize,
                self.people,
                self.state,
                self.global_must_win,
                self.excluded_ids,
                include_excluded=self.include_excluded,
                excluded_winner_range=self.excluded_winner_range,
                prizes=self.prizes,
            )
        except ValueError as exc:
            self.canvas.delete("visual_item")
            self.canvas.delete("result")
            self.canvas.delete("particle")
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                self.canvas.winfo_height() / 2,
                text=str(exc),
                fill="#ffffff",
                font=("Helvetica", 22, "bold"),
                tags="result",
            )
            return
        for winner in winners:
            self.drawn_ids.add(winner["person_id"])
        if self.on_complete:
            self.on_complete(winners)
        self.canvas.delete("visual_item")
        self.canvas.delete("result")
        self.canvas.delete("particle")
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        prize_name = getattr(self.prize, "name", "奖项")
        if winners:
            name_list = [f"{w['person_name']} ({w['person_id']})" for w in winners]
        else:
            name_list = ["未抽出新的中奖者"]
        self.canvas.create_oval(
            width * 0.18,
            height * 0.18,
            width * 0.82,
            height * 0.82,
            outline="#5ee1ff",
            width=4,
            tags="result",
        )
        self.canvas.create_rectangle(
            width * 0.18,
            height * 0.28,
            width * 0.82,
            height * 0.78,
            fill="#0d0f2b",
            outline="#ff5e5b",
            width=3,
            tags="result",
        )
        self.canvas.create_text(
            width / 2,
            height * 0.33,
            text=f"恭喜中奖 · {prize_name}",
            fill="#ffe66d",
            font=("Helvetica", 30, "bold"),
            tags="result",
        )
        if len(name_list) == 1 and name_list[0] == "未抽出新的中奖者":
            self.canvas.create_text(
                width / 2,
                height * 0.55,
                text=name_list[0],
                fill="#ffffff",
                font=("Helvetica", 24, "bold"),
                tags="result",
            )
        else:
            total = len(name_list)
            columns = 1
            if total > 20:
                columns = 3
            elif total > 10:
                columns = 2
            rows = math.ceil(total / columns)
            font_size = 24 if total <= 10 else 20 if total <= 20 else 18
            col_width = (width * 0.62) / columns
            start_x = width * 0.19 + col_width / 2
            start_y = height * 0.48
            for col in range(columns):
                start_index = col * rows
                end_index = min(start_index + rows, total)
                if start_index >= total:
                    break
                column_text = "\n".join(name_list[start_index:end_index])
                self.canvas.create_text(
                    start_x + col * col_width,
                    start_y,
                    text=column_text,
                    fill="#ffffff",
                    font=("Helvetica", font_size, "bold"),
                    tags="result",
                    anchor=tk.N,
                    justify=tk.LEFT,
                )
        self.canvas.create_text(
            width / 2,
            height * 0.72,
            text="年后尾牙幸运时刻",
            fill="#5ee1ff",
            font=("Helvetica", 18, "bold"),
            tags="result",
        )
        self._spawn_particles()
        if self.audio_ready and self.win_sound:
            try:
                self.win_sound.play()
            except pygame.error:
                pass
        self._refresh_prize_options()

    def _spawn_particles(self) -> None:
        self.particles = []
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        center_x = width / 2
        center_y = height / 2
        colors = ["#ff5e5b", "#ffe66d", "#00f5d4", "#9b5de5", "#f15bb5"]
        for _ in range(120):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2.5, 7.5)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            color = random.choice(colors)
            size = random.randint(4, 8)
            particle_id = self.canvas.create_oval(
                center_x - size,
                center_y - size,
                center_x + size,
                center_y + size,
                fill=color,
                outline="",
                tags="particle",
            )
            self.particles.append(
                {
                    "id": particle_id,
                    "vx": vx,
                    "vy": vy,
                    "life": random.randint(40, 70),
                }
            )

    def _build_ambient_layer(self) -> None:
        self.canvas.delete("ambient")
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        center_x = width / 2
        center_y = height / 2
        ring_outer = self.canvas.create_oval(
            center_x - width * 0.42,
            center_y - height * 0.42,
            center_x + width * 0.42,
            center_y + height * 0.42,
            outline="#1d3159",
            width=2,
            tags="ambient",
        )
        ring_inner = self.canvas.create_oval(
            center_x - width * 0.28,
            center_y - height * 0.28,
            center_x + width * 0.28,
            center_y + height * 0.28,
            outline="#1a2a4a",
            width=2,
            tags="ambient",
        )
        self.ambient_rings = [
            {"id": ring_outer, "speed": 0.6},
            {"id": ring_inner, "speed": -0.4},
        ]
        self.ambient_particles = []
        for _ in range(55):
            x = random.uniform(0, width)
            y = random.uniform(0, height)
            size = random.uniform(1.5, 3.5)
            color = random.choice(["#5ee1ff", "#f15bb5", "#00f5d4"])
            particle_id = self.canvas.create_oval(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=color,
                outline="",
                tags="ambient",
            )
            self.ambient_particles.append(
                {"id": particle_id, "vx": random.uniform(-0.4, 0.4), "vy": random.uniform(0.2, 0.8)}
            )
        self.canvas.tag_lower("ambient")
        if self.background_id is not None:
            self.canvas.tag_lower(self.background_id)

    def _animate_ambient(self) -> None:
        if not self.ambient_particles:
            return
        width = self.canvas.winfo_width() or 1200
        height = self.canvas.winfo_height() or 700
        for particle in self.ambient_particles:
            self.canvas.move(particle["id"], particle["vx"], particle["vy"])
            x1, y1, x2, y2 = self.canvas.coords(particle["id"])
            if y1 > height:
                offset = y2 - y1
                self.canvas.coords(particle["id"], x1, -offset, x2, 0)
            if x2 < 0:
                dx = width + (x2 - x1)
                self.canvas.move(particle["id"], dx, 0)
            if x1 > width:
                dx = -width - (x2 - x1)
                self.canvas.move(particle["id"], dx, 0)
        for ring in self.ambient_rings:
            pulse = abs(math.sin(time.monotonic() * ring["speed"])) * 0.6 + 0.4
            color_value = int(60 + pulse * 120)
            self.canvas.itemconfigure(ring["id"], outline=f"#1d{color_value:02x}ff")

    def _animate_particles(self) -> None:
        if not self.particles:
            return
        for particle in list(self.particles):
            self.canvas.move(particle["id"], particle["vx"], particle["vy"])
            particle["vy"] += 0.25
            particle["life"] -= 1
            if particle["life"] <= 0:
                self.canvas.delete(particle["id"])
                self.particles.remove(particle)

    def _build_display_names(self) -> list[str]:
        if not self.prize:
            return [person.name for person in self.people]
        excluded_must_win = self.global_must_win if self.prize.exclude_must_win else set()
        excluded_must_win = excluded_must_win - set(self.prize.must_win_ids)
        exclude_excluded_list = self.prize.exclude_excluded_list and not self.include_excluded
        names = [
            person.name
            for person in self.people
            if (
                (not exclude_excluded_list or person.person_id not in self.excluded_ids)
                and (not self.prize.exclude_previous_winners or person.person_id not in self.drawn_ids)
                and person.person_id not in excluded_must_win
            )
        ]
        return names

    def _refresh_prize_options(self) -> None:
        options = []
        for prize in self.prizes:
            remaining = remaining_slots(prize, self.state)
            options.append(f"{prize.prize_id} - {prize.name} (剩余 {remaining})")
        self.prize_combo["values"] = options
        current_label = self._format_prize_label(self.prize)
        if current_label in options:
            self.prize_var.set(current_label)
            return
        if options:
            self.prize_var.set(options[0])
        else:
            self.prize_var.set("")

    def update_prizes(self, prizes: list[Any], state: dict[str, Any]) -> None:
        """Update prize list and refresh combobox in real time."""
        self.prizes = prizes
        self.state = state
        self._refresh_prize_options()
        label = self.prize_var.get().strip()
        if label:
            prize_id = label.split(" - ", 1)[0]
            self.prize = next((item for item in self.prizes if item.prize_id == prize_id), None)
        if not self.prize and self.prizes:
            self.prize = self.prizes[0]
            self.prize_var.set(self._format_prize_label(self.prize))

    def _format_prize_label(self, prize: Any) -> str:
        if not prize:
            return ""
        remaining = remaining_slots(prize, self.state)
        return f"{prize.prize_id} - {prize.name} (剩余 {remaining})"

    def _handle_prize_change(self, event: tk.Event) -> None:
        label = self.prize_var.get().strip()
        if not label:
            return
        prize_id = label.split(" - ", 1)[0]
        prize = next((item for item in self.prizes if item.prize_id == prize_id), None)
        if prize:
            self.prize = prize
            self.state_mode = self.BOUNCE
            self.rotation_speed = 0.01
            self._build_bounce_items()
