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

import copy
import math
import random
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from typing import Any, Callable

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

from lottery import draw_prize, remaining_slots


class WheelLotteryWindow(tk.Toplevel):
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
        
        # --- 配色方案 (Cyberpunk Nebula) ---
        self.colors = {
            "bg_canvas": "#0F0B15",    
            "panel_bg": "#1A1625",     
            "panel_border": "#332a45", 
            "gold": "#FFD700",
            "cyan": "#00F5D4",
            "red": "#FF2E63",
            "text_main": "#FFFFFF",
            "wheel_colors": ["#FF2E63", "#00F5D4", "#F9F871", "#FF9F1C", "#9D4EDD"] 
        }
        self.configure(bg=self.colors["panel_bg"])

        # 变量
        self.title_text_var = tk.StringVar(value="✨ 2025 年度盛典 ✨")
        self.prize_var = tk.StringVar()
        self.result_var = tk.StringVar(value="等待蓄力...")
        
        # TTS
        self.tts_engine = None
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty('rate', 180) 
            except Exception:
                pass 

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
        self.decel_factor = 0.04    
        
        # 队列
        self.pending_winners: list[dict[str, Any]] = []
        self.target_queue: list[str] = [] 
        self.revealed_winners: list[str] = []
        self.removing_id: str | None = None
        self.removal_scale = 1.0
        self.post_removal_phase: str | None = None
        self.is_showing_prize_result = False
        self.removal_particles: list[dict[str, Any]] = []
        
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
        
        # --- 滚动条相关 (v21优化) ---
        self.scroll_after_id = None
        self.scroll_direction = 1 # 1向下, -1向上
        self.is_scroll_pausing = False
        self.summary_scroll_after_id = None
        self.summary_scroll_speed = 0.6
        self.summary_scroll_margin = 160
        
        self._build_ui()
        self._bind_controls()
        self._refresh_prize_options()
        self._refresh_history_list() 
        self._animate()
        self._start_auto_scroll() 

    def _create_particle(self):
        return {
            "x": random.random(),
            "y": random.random(),
            "size": random.randint(1, 3),
            "speed": random.uniform(0.0003, 0.0015),
            "color": random.choice(["#ffffff", "#00F5D4", "#FF2E63", "#443366"])
        }

    def _build_ui(self) -> None:
        """Frame + Grid 布局"""
        main_container = tk.Frame(self, bg=self.colors["panel_bg"])
        main_container.pack(fill=tk.BOTH, expand=True)

        # ================= 左侧面板 =================
        left_sidebar = tk.Frame(main_container, bg=self.colors["panel_bg"], width=320)
        left_sidebar.pack(side=tk.LEFT, fill=tk.Y)
        left_sidebar.pack_propagate(False)

        # 标题区
        title_frame = tk.Frame(left_sidebar, bg=self.colors["panel_bg"], pady=30)
        title_frame.pack(fill=tk.X)
        self.title_label = tk.Label(title_frame, textvariable=self.title_text_var, font=("Microsoft YaHei UI", 18, "bold"), bg=self.colors["panel_bg"], fg=self.colors["gold"], wraplength=300)
        self.title_label.pack()
        self.title_label.bind("<Double-Button-1>", self._edit_title)
        tk.Label(title_frame, text="(双击修改标题)", font=("Arial", 8), bg=self.colors["panel_bg"], fg="#666").pack(pady=2)

        tk.Label(left_sidebar, text="🏆 荣耀榜单", font=("Microsoft YaHei UI", 14), bg=self.colors["panel_bg"], fg="#EEE").pack(pady=(10, 5))

        self.history_listbox = tk.Listbox(
            left_sidebar, 
            bg="#231e2e", 
            fg="#EEE", 
            font=("Microsoft YaHei UI", 12), 
            highlightthickness=0, 
            borderwidth=0,
            activestyle="none"
        )
        self.history_listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # ================= 右侧面板 =================
        right_sidebar = tk.Frame(main_container, bg=self.colors["panel_bg"], width=340)
        right_sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        right_sidebar.pack_propagate(False)

        # 状态区
        status_frame = tk.Frame(right_sidebar, bg=self.colors["panel_bg"], pady=30, padx=20)
        status_frame.pack(fill=tk.X)
        tk.Label(status_frame, text="当前状态", bg=self.colors["panel_bg"], fg=self.colors["cyan"], font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W)
        self.status_label = tk.Label(status_frame, textvariable=self.result_var, bg=self.colors["panel_bg"], fg=self.colors["gold"], font=("Microsoft YaHei UI", 16, "bold"), wraplength=300, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, pady=(5, 0))

        # 本轮名单
        tk.Label(right_sidebar, text="🎉 本轮中奖", bg=self.colors["panel_bg"], fg=self.colors["red"], font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W, padx=20, pady=(20, 5))
        
        list_frame = tk.Frame(right_sidebar, bg="#333", padx=1, pady=1) 
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20)
        
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", bg="#222")
        self.winner_listbox = tk.Listbox(list_frame, bg="#150a21", fg="white", font=("Microsoft YaHei UI", 13), highlightthickness=0, borderwidth=0, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.winner_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.winner_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 底部控制
        ctrl_frame = tk.Frame(right_sidebar, bg=self.colors["panel_bg"], padx=20, pady=30)
        ctrl_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(ctrl_frame, text="选择奖项:", bg=self.colors["panel_bg"], fg="#AAA").pack(anchor=tk.W)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground="#333", background="#444", foreground="#fff", arrowcolor="white", font=("Microsoft YaHei UI", 12))
        
        self.prize_combo = ttk.Combobox(ctrl_frame, textvariable=self.prize_var, state="readonly", font=("Microsoft YaHei UI", 12))
        self.prize_combo.pack(fill=tk.X, pady=(2, 15), ipady=5)
        self.prize_combo.bind("<<ComboboxSelected>>", self._handle_prize_change)

        self.action_btn = tk.Button(ctrl_frame, text="按住蓄力 / 点击开始", bg=self.colors["gold"], fg="#000", font=("Microsoft YaHei UI", 16, "bold"), relief="flat", cursor="hand2")
        self.action_btn.pack(fill=tk.X, pady=(0, 10), ipady=10)
        self.action_btn.bind("<ButtonPress-1>", self._on_btn_down)
        self.action_btn.bind("<ButtonRelease-1>", self._on_btn_up)
        
        self.reset_btn = tk.Button(ctrl_frame, text="⟳ 重置名单 (清空队列)", command=self._prepare_wheel, bg="#444", fg="#FFF", font=("Microsoft YaHei UI", 10), relief="flat", cursor="hand2")
        self.reset_btn.pack(fill=tk.X)

        # ================= 中间画布 =================
        self.canvas = tk.Canvas(main_container, bg=self.colors["bg_canvas"], highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._render_wheel())

    def _edit_title(self, event):
        new_title = simpledialog.askstring("设置", "修改大屏标题：", initialvalue=self.title_text_var.get(), parent=self)
        if new_title:
            self.title_text_var.set(new_title)

    def _bind_controls(self):
        self.bind("<KeyPress-space>", self._on_key_down)
        self.bind("<KeyRelease-space>", self._on_key_up)
        self.bind("<F11>", self._toggle_fullscreen)
        self.focus_set()

    def _toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        if self.is_fullscreen:
            self.normal_geometry = self.geometry()
            screen_x, screen_y, screen_w, screen_h = self._get_current_screen_geometry()
            self.geometry(f"{screen_w}x{screen_h}+{screen_x}+{screen_y}")
        else:
            if self.normal_geometry:
                self.geometry(self.normal_geometry)
            else:
                self.geometry("1440x900")

    def _handle_close(self) -> None:
        if self.draw_after_id: self.after_cancel(self.draw_after_id)
        if self.scroll_after_id: self.after_cancel(self.scroll_after_id)
        if self.summary_scroll_after_id: self.after_cancel(self.summary_scroll_after_id)
        self.destroy()
        if self.on_close: self.on_close()

    # --- 自动滚动逻辑 (v21 修正版) ---
    def _start_auto_scroll(self):
        self.scroll_direction = 1 # 初始向下
        self.is_scroll_pausing = False
        self._auto_scroll_tick()

    def _history_overflows(self) -> bool:
        if self.history_listbox.size() == 0:
            return False
        height = self.history_listbox.winfo_height()
        if height <= 1:
            return False
        first_index = self.history_listbox.nearest(0)
        last_index = self.history_listbox.nearest(height - 1)
        visible_count = max(0, last_index - first_index + 1)
        return self.history_listbox.size() > visible_count

    def _auto_scroll_tick(self):
        if self.is_scroll_pausing:
            # 暂停中，暂不移动，仅循环等待
            self.scroll_after_id = self.after(50, self._auto_scroll_tick)
            return

        if self.history_listbox.size() > 0:
            if not self._history_overflows():
                self.scroll_after_id = self.after(200, self._auto_scroll_tick)
                return
            # 获取可视范围 (0.0 ~ 1.0)
            first_vis, last_vis = self.history_listbox.yview()
            
            # 只有当内容超出显示范围时(不能同时看到头和尾)，才需要滚动
            if not (first_vis <= 0.0 and last_vis >= 1.0):
                current_top = first_vis
                
                # 计算新位置
                # scroll_direction: 1 向下(数值变大), -1 向上(数值变小)
                move_step = 0.001 * self.scroll_direction
                new_pos = current_top + move_step
                
                # 边界检查
                if self.scroll_direction == 1:
                    # 向下滚动，检查底部
                    # 注意：yview_moveto 设置的是顶部的偏移量
                    # 我们需要检查 last_vis 是否到达 1.0
                    # 但 yview() 是获取当前状态，我们刚计算的是期望的 new_pos
                    # 简单做法：应用后检查，或者预判
                    
                    # 预判逻辑稍微复杂，直接移动后检查最简单，但容易抖动
                    # 这里使用逻辑推导：如果 last_vis 已经很接近 1.0
                    if last_vis >= 0.999:
                        self._trigger_scroll_pause_and_reverse(-1)
                        return # 退出本次 tick
                    
                else:
                    # 向上滚动，检查顶部
                    if new_pos <= 0.0:
                        new_pos = 0.0
                        self._trigger_scroll_pause_and_reverse(1)
                        # 应用 0.0
                        self.history_listbox.yview_moveto(0.0)
                        return

                self.history_listbox.yview_moveto(new_pos)

        self.scroll_after_id = self.after(50, self._auto_scroll_tick)

    def _trigger_scroll_pause_and_reverse(self, new_direction):
        """到达边界，暂停并反向"""
        self.is_scroll_pausing = True
        
        def _resume():
            self.scroll_direction = new_direction
            self.is_scroll_pausing = False
            
        # 暂停 2 秒
        self.after(2000, _resume)

    # --- 输入控制 ---
    def _on_input_down(self):
        if self.phase == "summary":
            return
        if self.phase == "removing":
            return
        if self.is_showing_prize_result:
            if self._has_next_prize():
                self._go_next_prize()
            else:
                self._render_grand_summary()
            return
        if self.phase == "prize_summary":
            if self._has_next_prize():
                self._go_next_prize()
            else:
                self._render_grand_summary()
            return
        if self.phase in ["spinning", "braking", "auto_wait", "removing"]:
            self._pause_game()
            return

        if (self.phase == "idle" or self.phase == "wait_for_manual") and not self.space_held:
            self.space_held = True
            self.charge_power = 0.0
            self.phase = "charging"
            self.result_var.set("⚡ 能量注入中...")
            self._update_btn_state()
            if not self.target_queue:
                self._start_draw_logic() 

    def _on_input_up(self):
        if self.phase == "charging":
            self.space_held = False
            self.phase = "spinning"
            self.is_auto_playing = True 
            
            # --- 核心：时间物理参数初始化 ---
            self.locked_charge = self.charge_power 
            self._init_time_physics(self.locked_charge)
            
            self.result_var.set("🚀 转盘转动中...")
            self._update_btn_state()
            
            if not self.target_queue:
                self.phase = "idle"
                self.result_var.set("无目标")
                self._update_btn_state()

    def _init_time_physics(self, power):
        self.spin_duration = 2.0 + (43.0 * power)
        self.spin_start_time = time.monotonic()
        
        base_brake = 5.0 + (5.0 * power)
        random_flux = random.uniform(-2.0, 2.0)
        self.brake_duration = max(3.0, base_brake + random_flux)
        
        self.current_speed = 30.0 

    def _on_key_down(self, event): self._on_input_down()
    def _on_key_up(self, event): self._on_input_up()
    def _on_btn_down(self, event): self._on_input_down()
    def _on_btn_up(self, event): self._on_input_up()

    def _pause_game(self):
        if self.phase in ["finished", "summary"]: return
        if not self.target_queue and self.phase not in ["spinning", "braking"]: return

        self.phase = "wait_for_manual" 
        self.is_auto_playing = False   
        self.current_speed = 0.0       
        self.result_var.set("⏸ 已暂停")
        self._update_btn_state()

    def _start_draw_logic(self) -> None:
        if not self.wheel_names:
            self._prepare_wheel()
            if not self.wheel_names:
                return
        prize_label = self.prize_var.get()
        if not prize_label: return
        prize_id = prize_label.split(" - ", 1)[0]
        prize = next((p for p in self.prizes if p.prize_id == prize_id), None)
        if not prize: return

        clean_excluded_ids = set()
        for item in self.excluded_ids:
            if hasattr(item, 'person_id'): clean_excluded_ids.add(str(item.person_id))
            else: clean_excluded_ids.add(str(item))
        already_won_ids = {str(winner["person_id"]) for winner in self.lottery_state.get("winners", [])}
        clean_excluded_ids |= already_won_ids

        remaining = remaining_slots(prize, self.lottery_state)
        if remaining <= 0:
            return

        preview_state = copy.deepcopy(self.lottery_state)
        winners = draw_prize(prize, self.people, preview_state, self.global_must_win, clean_excluded_ids)

        if not winners:
            self.phase = "idle"
            messagebox.showinfo("结果", "未能抽出中奖者。")
            return

        self.pending_winners = [] 
        self.target_queue = []

        for winner in winners:
            target_id = str(winner["person_id"])
            target_idx = next((item["index"] for item in self.wheel_names if str(item["id"]) == target_id), -1)
            if target_idx != -1:
                self.pending_winners.append(winner)
                self.target_queue.append(target_id)

        if not self.target_queue:
            self.phase = "idle"
            self.result_var.set("无目标")
            self._update_btn_state()

    def _prepare_wheel(self) -> None:
        if self.phase == "wait_for_manual":
            self.target_queue = [] 
        elif self.target_queue or self.phase not in ["idle", "finished", "summary"]:
             return

        self.is_auto_playing = True 
        label = self.prize_var.get().strip()
        if not label: return
        prize_id = label.split(" - ", 1)[0]
        prize = next((p for p in self.prizes if p.prize_id == prize_id), None)
        if not prize: return

        prize_must_win_set = set(prize.must_win_ids)
        excluded_must_win = self.global_must_win - prize_must_win_set if prize.exclude_must_win else set()
        previous_winners_set = {str(w["person_id"]) for w in self.lottery_state["winners"]}
        clean_excluded_ids = set()
        for item in self.excluded_ids:
            if hasattr(item, 'person_id'): clean_excluded_ids.add(str(item.person_id))
            else: clean_excluded_ids.add(str(item))

        blacklist = clean_excluded_ids | excluded_must_win | previous_winners_set
        
        eligible = []
        for p in self.people:
            if str(p.person_id) not in blacklist: eligible.append(p)

        if not eligible:
            self.wheel_names = []
            self.result_var.set("无候选人")
            self.winner_listbox.delete(0, tk.END)
            self._render_wheel()
            return

        random.shuffle(eligible)
        
        total = len(eligible)
        self.segment_angle = 360.0 / total
        self.wheel_names = []
        random_colors = copy.copy(self.colors["wheel_colors"])
        
        for i, person in enumerate(eligible):
            dept = getattr(person, 'department', '')
            full_text = f"{dept} {person.person_id} {person.name}".strip()
            self.wheel_names.append({
                "index": i,
                "id": str(person.person_id),
                "name": person.name,
                "full_text": full_text,
                "color": random_colors[i % len(random_colors)],
                "angle_center": i * self.segment_angle + self.segment_angle / 2
            })

        self.phase = "idle"
        self.wheel_rotation = 0.0 
        self.result_var.set(f"就绪 | {prize.name}")
        self.winner_listbox.delete(0, tk.END)
        self.revealed_winners = []
        self._update_btn_state()
        self._render_wheel()

    def _animate(self) -> None:
        """主循环"""
        current_time = time.monotonic()
        dt = current_time - self.last_time
        self.last_time = current_time
        self.anim_frame += 1
        if dt > 0.05: dt = 0.05

        # 粒子
        for p in self.bg_particles:
            p["x"] += p["speed"] * 0.5
            p["y"] += p["speed"]
            if p["x"] > 1.0: p["x"] = 0
            if p["y"] > 1.0: p["y"] = 0

        # --- 物理逻辑 V3 ---
        display_energy = 0.0 

        if self.phase == "charging":
            self.charge_power += self.charge_speed
            if self.charge_power > 1.0: self.charge_power = 1.0
            display_energy = self.charge_power 
            
            shake = (random.random() - 0.5) * 3.0 * self.charge_power
            self.wheel_rotation += shake
            
            if self.charge_power < 0.3: self.encouragement_text = "⚡ 蓄力..."
            elif self.charge_power < 0.6: self.encouragement_text = "🔥 能量注入"
            elif self.charge_power < 0.9: self.encouragement_text = "⚠️ 高能！"
            else: self.encouragement_text = "🚀 MAX"

        elif self.phase == "spinning":
            elapsed = current_time - self.spin_start_time
            if elapsed < self.spin_duration:
                progress = elapsed / self.spin_duration
                display_energy = self.locked_charge * (1.0 - progress)
                self.current_speed = 30.0 + math.sin(current_time * 5) * 0.5
                self.wheel_rotation += self.current_speed
            else:
                self.phase = "braking"
                self._calculate_stop_path_by_time() 

        elif self.phase == "braking":
            display_energy = 0
            dist_remaining = self.target_rotation - self.wheel_rotation
            step = dist_remaining * self.decel_factor
            
            min_speed = 0.1
            if step < min_speed: step = min_speed
            if step > dist_remaining: step = dist_remaining

            self.wheel_rotation += step
            
            if dist_remaining < 0.2:
                self.wheel_rotation = self.target_rotation 
                self._handle_stop()
        
        elif self.phase == "auto_wait":
            if self.anim_frame % 5 == 0: self._create_firework()
            
            if current_time - self.auto_wait_start_time > self.auto_wait_duration:
                if self.target_queue:
                    self.phase = "spinning"
                    self._init_time_physics(self.locked_charge)
                    self.result_var.set("自动连抽中...")
                    self._update_btn_state()
                else:
                    self._show_prize_summary_if_complete()
        elif self.phase == "removing":
            self.removal_scale -= 0.08
            if self.removal_scale <= 0:
                self._finalize_removal()
            self._animate_removal_particles()
        else:
            self._animate_removal_particles()

        self._render_wheel(display_energy)
        self.draw_after_id = self.after(20, self._animate)
    
    def _calculate_stop_path_by_time(self):
        if not self.target_queue: return
        target_id = self.target_queue[0]
        item = next((entry for entry in self.wheel_names if str(entry["id"]) == str(target_id)), None)
        if not item:
            self._prepare_wheel()
            item = next((entry for entry in self.wheel_names if str(entry["id"]) == str(target_id)), None)
        if not item:
            self.target_queue.pop(0)
            return
        target_center_angle = item["angle_center"]
        
        desired_mod = (90 - target_center_angle) % 360
        current_abs = self.wheel_rotation
        current_mod = current_abs % 360
        rotation_needed = (desired_mod - current_mod) % 360
        
        avg_speed = 10.0 
        estimated_dist = avg_speed * (self.brake_duration * 50) 
        
        extra_spins = math.ceil(estimated_dist / 360) * 360
        
        self.target_rotation = current_abs + rotation_needed + extra_spins
        self.decel_factor = 0.04 

    def _render_grand_summary(self):
        self.phase = "summary"
        self.result_var.set("🎉 所有奖项抽取完毕！")
        self.canvas.delete("all")
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_rectangle(0, 0, width, height, fill="#110517", outline="")
        
        self.canvas.create_text(width/2, 100, text="🏆 中奖总榜 🏆", font=("Microsoft YaHei UI", 36, "bold"), fill=self.colors["gold"])

        y_start = 180
        winners = self.lottery_state.get("winners", [])
        
        grouped = {}
        for w in winners:
            p_name = w.get('prize_name', '未知奖项')
            if p_name not in grouped: grouped[p_name] = []
            grouped[p_name].append(w.get('person_name'))

        ordered_prizes = []
        for prize in self.prizes:
            if prize.name in grouped:
                ordered_prizes.append((prize.name, grouped[prize.name]))
        for prize_name, names in grouped.items():
            if prize_name not in {item[0] for item in ordered_prizes}:
                ordered_prizes.append((prize_name, names))

        columns = 3
        column_width = width / columns
        column_positions = [column_width * (i + 0.5) for i in range(columns)]
        column_heights = [y_start] * columns

        header_height = 28
        line_height = 20
        block_gap = 26

        for idx, (prize_name, names) in enumerate(ordered_prizes):
            col = idx % columns
            x = column_positions[col]
            y = column_heights[col]
            self.canvas.create_text(
                x,
                y,
                text=f"✨ {prize_name}",
                font=("Microsoft YaHei UI", 18, "bold"),
                fill=self.colors["cyan"],
                anchor="n",
                tags="summary_items",
            )
            names_text = "\n".join(names) if names else "暂无"
            self.canvas.create_text(
                x,
                y + header_height,
                text=names_text,
                font=("Microsoft YaHei UI", 14),
                fill="white",
                anchor="n",
                tags="summary_items",
            )
            names_lines = max(1, len(names))
            block_height = header_height + names_lines * line_height + block_gap
            column_heights[col] += block_height

        self._start_summary_scroll(max(column_heights), height)

    def _render_prize_summary(self, prize) -> None:
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_rectangle(0, 0, width, height, fill="#110517", outline="")

        title_text = f"🎉 {prize.name} 中奖结果"
        self.canvas.create_text(width / 2, 90, text=title_text, font=("Microsoft YaHei UI", 32, "bold"), fill=self.colors["gold"])

        winners = [
            winner for winner in self.lottery_state.get("winners", [])
            if winner.get("prize_id") == prize.prize_id
        ]
        names = [winner.get("person_name", "未知") for winner in winners]
        if not names:
            self.canvas.create_text(width / 2, height / 2, text="暂无中奖者", font=("Microsoft YaHei UI", 22, "bold"), fill="white")
            return

        total = len(names)
        columns = 3 if total > 20 else 2 if total > 10 else 1
        column_width = width / columns
        column_positions = [column_width * (i + 0.5) for i in range(columns)]
        rows = math.ceil(total / columns)
        font_size = 20 if total <= 10 else 18 if total <= 24 else 16

        start_y = 160
        for col in range(columns):
            start_index = col * rows
            end_index = min(start_index + rows, total)
            if start_index >= total:
                break
            column_text = "\n".join(names[start_index:end_index])
            self.canvas.create_text(
                column_positions[col],
                start_y,
                text=column_text,
                font=("Microsoft YaHei UI", font_size, "bold"),
                fill="white",
                anchor="n",
                justify=tk.LEFT,
            )

    def _start_summary_scroll(self, content_height: float, canvas_height: float) -> None:
        if self.summary_scroll_after_id:
            self.after_cancel(self.summary_scroll_after_id)
            self.summary_scroll_after_id = None

        visible_height = canvas_height - self.summary_scroll_margin
        if content_height <= visible_height:
            return

        def _tick():
            if self.phase != "summary":
                return
            self.canvas.move("summary_items", 0, -self.summary_scroll_speed)
            bbox = self.canvas.bbox("summary_items")
            if bbox and bbox[3] < self.summary_scroll_margin:
                reset_y = canvas_height + 40
                self.canvas.move("summary_items", 0, reset_y - bbox[1])
            self.summary_scroll_after_id = self.after(40, _tick)

        self.summary_scroll_after_id = self.after(40, _tick)

    def _speak_winner(self, text):
        if not self.tts_engine: return
        def _speak():
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception:
                pass
        threading.Thread(target=_speak, daemon=True).start()

    def _handle_stop(self):
        if not self.target_queue: return
        winner_id = str(self.target_queue.pop(0))
        winner_data = next((entry for entry in self.wheel_names if str(entry["id"]) == winner_id), None)
        if not winner_data:
            return
        info = winner_data['full_text']
        winner_entry = self.pending_winners.pop(0) if self.pending_winners else None
        self.revealed_winners.append(info)
        self.winner_listbox.insert(tk.END, f"🏆 {info}")
        self.winner_listbox.see(tk.END) 
        
        if winner_entry:
            self._apply_winner_to_state(winner_entry)
            if self.on_transfer:
                self.on_transfer(self.lottery_state, [winner_entry])
        
        try:
            prize_label = self.prize_var.get().split(" - ")[1].split(" (")[0]
        except Exception:
            prize_label = "奖品"
            
        self.result_var.set(f"恭喜 {winner_data['name']} 获得 {prize_label}！")
        
        parts = info.split(' ')
        speak_text = f"恭喜 {parts[-1]} 获得 {prize_label}"
        self._speak_winner(speak_text)
        self._refresh_history_list() 

        self.removing_id = str(winner_data["id"])
        self.removal_scale = 1.0
        self._spawn_removal_particles(winner_data)
        if not self.target_queue and self._is_current_prize_complete():
            self.post_removal_phase = "prize_summary"
        elif self.is_auto_playing:
            self.post_removal_phase = "auto_wait"
        else:
            self.post_removal_phase = "wait_for_manual"
        self.phase = "removing"
        self._update_btn_state()

    def _apply_winner_to_state(self, winner: dict[str, Any]) -> None:
        if not winner:
            return
        prize_state = self.lottery_state.setdefault("prizes", {}).setdefault(winner["prize_id"], {"winners": []})
        if winner["person_id"] not in prize_state["winners"]:
            prize_state["winners"].append(winner["person_id"])
        self.lottery_state.setdefault("winners", []).append(winner)

    def update_prizes(self, prizes: list[Any], state: dict[str, Any]) -> None:
        self.prizes = prizes
        self.lottery_state = state
        
        current_val = self.prize_var.get()
        current_id = current_val.split(" - ")[0] if current_val else None
        
        self._refresh_prize_options()
        self._refresh_history_list()
        
        is_busy = bool(self.target_queue) or (self.phase not in ["idle", "finished", "wait_for_manual"])
        
        if current_id:
            if not is_busy:
                self.select_prize_by_id(current_id)
            else:
                options = self.prize_combo["values"]
                target_option = next((opt for opt in options if opt.startswith(f"{current_id} - ")), None)
                if target_option:
                    self.prize_var.set(target_option)

    def select_prize_by_id(self, prize_id: str) -> None:
        options = self.prize_combo["values"]
        target_option = next((opt for opt in options if opt.startswith(f"{prize_id} - ")), None)
        if target_option:
            self.prize_var.set(target_option)
            self._prepare_wheel()

    def _refresh_prize_options(self) -> None:
        options = []
        for prize in self.prizes:
            remaining = remaining_slots(prize, self.lottery_state)
            if remaining > 0:
                options.append(f"{prize.prize_id} - {prize.name} (剩余 {remaining})")
            
        self.prize_combo["values"] = options
        
        current = self.prize_var.get()
        if options and (not current or current not in options):
            self.prize_var.set(options[0])
            self._prepare_wheel()
        elif not options:
            self.prize_var.set("") 

    def _refresh_history_list(self) -> None:
        if not hasattr(self, "history_listbox"): return
        self.history_listbox.delete(0, tk.END)
        
        winners = self.lottery_state.get("winners", [])
        for w in reversed(winners):
            name = w.get('person_name', '未知')
            prize = w.get('prize_name', '奖品')
            self.history_listbox.insert(tk.END, f"🎗 {prize} - {name}")

    def _handle_prize_change(self, event: tk.Event) -> None:
        if self.phase in ["idle", "finished", "wait_for_manual", "prize_summary"]:
             self.target_queue = [] 
             self._prepare_wheel()

    # ---------------- 渲染 ----------------
    def _create_firework(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        x = random.randint(50, width-50)
        y = random.randint(50, height-50)
        color = random.choice(self.colors["wheel_colors"])
        size = random.randint(5, 15)
        self.canvas.create_oval(x, y, x+size, y+size, fill=color, tags="firework")
        self.root.after(500, lambda: self.canvas.delete("firework"))

    def _draw_text_with_outline(self, x, y, text, font, text_color, outline_color, thickness=2, tags=None, justify=tk.CENTER):
        for dx in range(-thickness, thickness+1):
            for dy in range(-thickness, thickness+1):
                if dx == 0 and dy == 0: continue
                self.canvas.create_text(x+dx, y+dy, text=text, font=font, fill=outline_color, tags=tags, justify=justify)
        self.canvas.create_text(x, y, text=text, font=font, fill=text_color, tags=tags, justify=justify)

    def _render_wheel(self, display_energy=0.0) -> None:
        if self.phase in ["summary", "prize_summary"]: return 

        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        for p in self.bg_particles:
            px = p["x"] * width
            py = p["y"] * height
            r = p["size"]
            self.canvas.create_oval(px, py, px+r, py+r, fill=p["color"], outline="")

        top_margin = 150
        max_diameter = min(width - 40, height - top_margin - 50)
        radius = max_diameter / 2
        cx = width / 2
        cy = top_margin + radius 
        
        if not self.wheel_names:
            self.canvas.create_text(cx, cy, text="暂无数据", fill="#555", font=("Microsoft YaHei UI", 20))
            return

        total_names = len(self.wheel_names)
        show_small_text = total_names <= 200
        
        if total_names >= 160: base_font_size = 6
        elif total_names >= 120: base_font_size = 8
        elif total_names >= 100: base_font_size = 10
        elif total_names >= 80: base_font_size = 12
        else: base_font_size = 14
        
        rotation_mod = self.wheel_rotation % 360
        pointer_text_top = ""

        for item in self.wheel_names:
            segment_extent = self.segment_angle
            segment_half = self.segment_angle / 2
            if self.phase == "removing" and self.removing_id and str(item["id"]) == self.removing_id:
                segment_extent = self.segment_angle * max(0.0, self.removal_scale)
                segment_half = segment_extent / 2
            start = (item["angle_center"] - segment_half + rotation_mod) % 360
            self.canvas.create_arc(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                start=start,
                extent=segment_extent,
                fill=item["color"],
                outline=item["color"],
                width=1,
            )
            
            mid_angle = (item["angle_center"] + rotation_mod) % 360
            dist_to_90 = abs(mid_angle - 90)
            if dist_to_90 < self.segment_angle / 2:
                pointer_text_top = item["full_text"]

            if show_small_text:
                mid_angle_rad = math.radians(mid_angle)
                text_radius = radius * 0.8
                tx = cx + text_radius * math.cos(mid_angle_rad)
                ty = cy - text_radius * math.sin(mid_angle_rad)
                display_on_wheel = item["name"]
                if total_names < 50: display_on_wheel = f"{item['name']}"
                text_angle = mid_angle
                if 90 < mid_angle < 270: text_angle += 180
                self.canvas.create_text(tx, ty, text=display_on_wheel, font=("Microsoft YaHei UI", base_font_size, "bold"), fill="#1a1c29", angle=text_angle)

        self.canvas.create_oval(cx - 70, cy - 70, cx + 70, cy + 70, fill="#ffffff", outline=self.colors["gold"], width=4)
        
        center_text_big = "LUCKY"
        center_text_small = ""
        prize_label = self.prize_var.get()
        if prize_label:
            try:
                parts = prize_label.split(" - ")
                if len(parts) > 1:
                    raw_name = parts[1]
                    if " (" in raw_name:
                        p_name = raw_name.split(" (")[0]
                        count_part = raw_name.split("剩余 ")[1].split(")")[0]
                        center_text_big = p_name
                        center_text_small = f"剩 {count_part} 个"
            except Exception:
                pass
        
        self._draw_text_with_outline(cx, cy - 10, center_text_big, ("Microsoft YaHei UI", 24, "bold"), self.colors["red"], "white", thickness=2)
        self.canvas.create_text(cx, cy + 25, text=center_text_small, font=("Microsoft YaHei UI", 12, "bold"), fill="#555")

        self.canvas.create_polygon(cx, cy - radius + 50, cx - 15, cy - radius + 10, cx + 15, cy - radius + 10, fill=self.colors["red"], outline="white", width=2)
        
        if pointer_text_top:
            bg_rect_y = cy - radius - 80
            self.canvas.create_rectangle(cx - 250, bg_rect_y, cx + 250, bg_rect_y + 60, fill="#221833", outline=self.colors["cyan"], width=2, tags="overlay")
            self.canvas.create_text(cx, bg_rect_y + 30, text=pointer_text_top, font=("Microsoft YaHei UI", 24, "bold"), fill=self.colors["gold"], tags="overlay")
            self.canvas.tag_raise("overlay")

        self._render_removal_particles()

        if self.phase != "finished":
            bar_w = 40
            bar_max_h = 400
            bar_x = width - 60 
            bar_bottom_y = height - 50 
            
            self.canvas.create_rectangle(bar_x, bar_bottom_y - bar_max_h, bar_x + bar_w, bar_bottom_y, outline="#333", width=2, fill="#111")
            
            fill_h = bar_max_h * display_energy
            if fill_h < 0: fill_h = 0
            fill_top_y = bar_bottom_y - fill_h
            
            if display_energy > 0.7: bar_color = self.colors["red"] 
            elif display_energy > 0.3: bar_color = self.colors["gold"]
            else: bar_color = self.colors["cyan"]
            
            self.canvas.create_rectangle(bar_x, fill_top_y, bar_x + bar_w, bar_bottom_y, fill=bar_color, outline="")
            
            if self.phase == "charging":
                self.canvas.create_text(bar_x - 15, fill_top_y, text=self.encouragement_text, fill="white", font=("Microsoft YaHei UI", 16, "bold"), anchor="e")
            
            self.canvas.create_text(bar_x + bar_w/2, bar_bottom_y + 25, text="动能", fill="#888", font=("Microsoft YaHei UI", 9))

    def _get_current_prize(self):
        label = self.prize_var.get()
        if not label:
            return None
        prize_id = label.split(" - ", 1)[0]
        return next((prize for prize in self.prizes if prize.prize_id == prize_id), None)

    def _has_next_prize(self) -> bool:
        return self._next_available_prize() is not None

    def _next_available_prize(self):
        current_prize = self._get_current_prize()
        start_index = -1
        if current_prize:
            start_index = next((i for i, prize in enumerate(self.prizes) if prize.prize_id == current_prize.prize_id), -1)
        for prize in self.prizes[start_index + 1:]:
            if remaining_slots(prize, self.lottery_state) > 0:
                return prize
        return None

    def _go_next_prize(self) -> None:
        next_prize = self._next_available_prize()
        if not next_prize:
            self._render_grand_summary()
            return
        options = self.prize_combo["values"]
        next_option = next((opt for opt in options if opt.startswith(f"{next_prize.prize_id} - ")), None)
        if next_option:
            self.prize_var.set(next_option)
            self._prepare_wheel()
            self.phase = "wait_for_manual"
            self.result_var.set(f"已切换至：{next_prize.name}，请蓄力开始！")
            self._update_btn_state()

    def _is_current_prize_complete(self) -> bool:
        current_prize = self._get_current_prize()
        if not current_prize:
            return False
        return remaining_slots(current_prize, self.lottery_state) <= 0

    def _show_prize_summary_if_complete(self) -> None:
        current_prize = self._get_current_prize()
        if not current_prize:
            return
        remaining = remaining_slots(current_prize, self.lottery_state)
        if remaining > 0:
            self.phase = "wait_for_manual"
            self.result_var.set(f"当前奖项剩余 {remaining} 个，请蓄力继续")
            self.is_showing_prize_result = False
            self._update_btn_state()
            return
        self.phase = "prize_summary"
        self.is_showing_prize_result = True
        self.result_var.set("本奖项已完成，查看结果或进入下一轮")
        self._render_prize_summary(current_prize)
        self._update_btn_state()

    def _update_btn_state(self):
        if self.phase == "prize_summary":
            if self._has_next_prize():
                self.action_btn.config(text="下一项", bg=self.colors["cyan"], fg="#000")
            else:
                self.action_btn.config(text="展示所有中奖者", bg=self.colors["cyan"], fg="#000")
            self.prize_combo.config(state="readonly")
        elif self.phase in ["charging", "spinning", "braking", "auto_wait", "removing"]:
            self.action_btn.config(text="STOP (点击暂停)", bg=self.colors["red"], fg="white")
            self.prize_combo.config(state="disabled") 
        elif self.phase == "wait_for_manual":
             self.action_btn.config(text="继续 (长按蓄力)", bg="#666", fg="#FFF")
             self.prize_combo.config(state="readonly") 
        else:
            self.action_btn.config(text="按住蓄力 / 点击开始", bg=self.colors["gold"], fg="black")
            self.prize_combo.config(state="readonly")

        if self.phase in ["idle", "wait_for_manual", "prize_summary"]:
            self.reset_btn.pack(fill=tk.X, pady=0, before=self.action_btn)
        else:
            self.reset_btn.pack_forget()

    def _get_current_screen_geometry(self) -> tuple[int, int, int, int]:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        screen_x = root_x - (root_x % screen_w)
        screen_y = root_y - (root_y % screen_h)
        return screen_x, screen_y, screen_w, screen_h

    def _finalize_removal(self) -> None:
        if self.removing_id:
            self._rebuild_wheel_layout(self.removing_id)
        self.removing_id = None
        self.removal_scale = 1.0
        if self.post_removal_phase == "prize_summary":
            self.phase = "prize_summary"
            self.is_showing_prize_result = True
            current_prize = self._get_current_prize()
            if current_prize:
                self._render_prize_summary(current_prize)
            self.result_var.set("本奖项已完成，查看结果或进入下一轮")
        elif self.post_removal_phase == "auto_wait":
            self.phase = "auto_wait"
            self.auto_wait_start_time = time.monotonic()
            self.is_showing_prize_result = False
        elif self.post_removal_phase == "wait_for_manual":
            self.phase = "wait_for_manual"
            self.is_showing_prize_result = False
        else:
            self.phase = "idle"
            self.is_showing_prize_result = False
        self.post_removal_phase = None
        self._update_btn_state()

    def _rebuild_wheel_layout(self, removed_id: str) -> None:
        self.wheel_names = [item for item in self.wheel_names if str(item["id"]) != removed_id]
        if self.wheel_names:
            self.segment_angle = 360.0 / len(self.wheel_names)
            for i, item in enumerate(self.wheel_names):
                item["index"] = i
                item["angle_center"] = i * self.segment_angle + self.segment_angle / 2
        else:
            self.segment_angle = 0.0

    def _spawn_removal_particles(self, winner_data: dict[str, Any]) -> None:
        if not winner_data:
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        top_margin = 150
        max_diameter = min(width - 40, height - top_margin - 50)
        radius = max_diameter / 2
        cx = width / 2
        cy = top_margin + radius
        color = winner_data.get("color", self.colors["gold"])
        for _ in range(26):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2.5, 6.0)
            self.removal_particles.append(
                {
                    "x": cx,
                    "y": cy,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed,
                    "life": random.randint(18, 32),
                    "size": random.randint(3, 6),
                    "color": color,
                }
            )

    def _animate_removal_particles(self) -> None:
        if not self.removal_particles:
            return
        for particle in list(self.removal_particles):
            particle["x"] += particle["vx"]
            particle["y"] += particle["vy"]
            particle["vy"] += 0.15
            particle["life"] -= 1
            if particle["life"] <= 0:
                self.removal_particles.remove(particle)

    def _render_removal_particles(self) -> None:
        for particle in self.removal_particles:
            x = particle["x"]
            y = particle["y"]
            size = particle["size"]
            self.canvas.create_oval(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=particle["color"],
                outline="",
            )
