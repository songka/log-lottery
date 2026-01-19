#!/usr/bin/env python3
"""
Wheel-based lottery window with Ping-Pong Auto-Scroll and Manual-Start Prize Switching.
优化版 v22：
1. 【荣耀榜滚动】：仅在内容溢出时触发“上下往复”滚动。
2. 【自动连抽】：单次启动后自动排队抽完当前奖项剩余名额。
3. 【切奖逻辑】：当前奖项抽完后自动切换，但进入等待状态需手动蓄力再开始。
4. 【总榜优化】：3 列布局 + 向上循环滚动。
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Callable

from wheel_window_logic import WheelWindowLogic
from wheel_window_particles import WheelWindowParticles
from wheel_window_prize import WheelWindowPrize
from wheel_window_render import WheelWindowRender
from wheel_window_scroll import WheelWindowScroll
from wheel_window_ui import WheelWindowUI


class WheelLotteryWindow(
    tk.Toplevel,
    WheelWindowUI,
    WheelWindowScroll,
    WheelWindowPrize,
    WheelWindowLogic,
    WheelWindowRender,
    WheelWindowParticles,
):
    """Lottery window specifically designed for Projector/Big Screen."""

    def __init__(
        self,
        root: tk.Tk,
        prizes: list[Any],
        people: list[Any],
        state: dict[str, Any],
        global_must_win: set[str],
        excluded_ids: set[str] | list[Any],
        on_transfer: Callable[[dict[str, Any], list[dict[str, Any]]], None],
        on_close: Callable[[], None],
    ) -> None:
        super().__init__(root)
        self.root = root
        self.prizes = prizes
        self.people = people
        self.lottery_state = state 
        self.global_must_win = global_must_win
        self.excluded_ids = excluded_ids
        self.on_transfer = on_transfer
        self.on_close = on_close

        self.title("幸运大转盘 - 终极版")
        
        # 默认大窗口
        self.geometry("1440x900")
        self.is_fullscreen = False
        self.normal_geometry = ""
        
        # --- 配色方案 (喜庆红金主题) ---  # Bug5: 替换整体 UI 为红金风格
        self.colors = {
            "bg_canvas": "#4A0C0C",
            "panel_bg": "#5C1010",
            "panel_border": "#8B1A1A",
            "gold": "#F7D774",
            "gold_deep": "#D9A441",
            "white": "#FFF8E7",
            "red": "#E53935",
            "red_deep": "#B71C1C",
            "accent": "#FFD700",
            "text_main": "#FFF8E7",
            "text_muted": "#F6D9B8",
            "wheel_colors": ["#E53935", "#C62828", "#F4C542", "#FF8A65", "#FFD54F"],
        }
        self.configure(bg=self.colors["panel_bg"])

        # 变量
        self.title_text_var = tk.StringVar(value="✨ 2025 年度盛典 ✨")
        self.prize_var = tk.StringVar()
        self.result_var = tk.StringVar(value="等待蓄力...")
        
        # --- 核心状态 ---
        self.phase = "idle" 
        self.is_auto_playing = True 
        
        # --- 物理/动画参数 ---
        self.wheel_rotation = 0.0 
        self.current_speed = 0.0
        self.wheel_names: list[dict] = [] 
        self.segment_angle = 0.0
        
        # 物理引擎 V3
        self.charge_power = 0.0     
        self.locked_charge = 0.0    
        self.charge_speed = 0.015   
        self.space_held = False    
        
        self.spin_start_time = 0.0  
        self.spin_duration = 0.0    
        self.brake_duration = 0.0   
        
        self.target_rotation = 0.0
        self.target_rotation_base = 0.0
        self.overshoot_angle = 0.0
        self.active_target_id: str | None = None
        self.brake_phase = "braking"
        self.osc_start_time = 0.0
        self.osc_A = 0.0
        self.osc_omega = 12.0
        self.osc_zeta = 0.25
        self.osc_min_duration = 0.6
        self.brake_start_time = 0.0
        self.brake_start_rotation = 0.0
        self.decel_factor = 0.04    
        
        # 队列
        self.pending_winners: list[dict[str, Any]] = []
        self.target_queue: list[str] = [] 
        self.revealed_winners: list[str] = []
        self.removing_idx = -1
        self.removal_scale = 1.0
        self.post_removal_phase: str | None = None
        self.is_showing_prize_result = False
        self.tts_playing = False
        self.tts_done_event = threading.Event()
        self.tts_lock = threading.Lock()
        self.tts_done_event.set()
        self.pending_removal_data: dict[str, Any] | None = None
        self.pending_removal_idx = -1
        self.removal_particles: list[dict[str, Any]] = []
        self.pending_removal_data: dict[str, Any] | None = None
        
        # 视觉特效
        self.bg_particles = [] 
        for _ in range(40):
            self.bg_particles.append(self._create_particle())

        # 计时器
        self.last_time = 0.0
        self.auto_wait_start_time = 0.0
        self.auto_wait_duration = 2.0 
        self.draw_after_id: str | None = None
        self.anim_frame = 0 
        self.render_after_id: str | None = None
        self._pending_resize_render = False
        self._last_resize_render_time = 0.0
        self._last_resize_event = 0.0
        self._resize_render_after_id: str | None = None
        self.pending_display_energy = 0.0
        self.render_interval_ms = 33
        self.last_render_time = 0.0
        self.last_bg_render_time = 0.0
        self.last_text_render_time = 0.0
        self.bg_update_interval = 0.12
        self.text_update_interval = 0.12
        self.text_render_mode = "off"
        self.force_full_render = False
        self.last_canvas_size = (0, 0)
        self.text_focus_angle = 22.0
        self.text_speed_off = 18.0
        self.text_speed_simple = 8.0
        self.max_text_items = 80
        
        # --- 滚动条相关 (v21优化) ---
        self.scroll_after_id = None
        self.scroll_direction = 1 # 1向下, -1向上
        self.is_scroll_pausing = False
        self.summary_scroll_after_id = None
        self.summary_scroll_speed = 0.6
        self.summary_scroll_margin = 160
        
        self._build_ui()
        self._bind_controls()
        self._refresh_prize_options(hide_completed=True)
        self._refresh_history_list() 
        self._animate()
        self._start_auto_scroll() 
