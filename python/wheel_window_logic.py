#!/usr/bin/env python3
"""Core logic for the wheel window."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import math
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any

_pyttsx3_spec = importlib.util.find_spec("pyttsx3")
if _pyttsx3_spec is None:
    pyttsx3 = None
    TTS_AVAILABLE = False
else:
    pyttsx3 = importlib.import_module("pyttsx3")
    TTS_AVAILABLE = True

from lottery import draw_prize, remaining_slots


class WheelWindowLogic:
    # --- 输入控制 ---
    def _on_input_down(self):
        if self.phase != "prize_summary":
            remaining = self._current_prize_remaining()
            if remaining <= 0:
                self.result_var.set("该奖项名额为0，请切换奖项")
                self._update_btn_state()
                return
        if self.tts_playing:
            return
        if self.phase == "summary":
            return
        if self.phase == "announce":
            return
        if self.phase == "removing":
            return
        if self.phase == "announcing":
            return
        if self.phase == "prize_summary":
            self._confirm_prize_result()
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
            #self._reset_round_display()
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
        self.spin_duration = 1.0 + (4.0 * power)
        self.spin_start_time = time.monotonic()
        
        base_brake = 2.0 + (2.5 * power)
        random_flux = random.uniform(-0.8, 0.8)
        self.brake_duration = max(1.5, base_brake + random_flux)
        
        self.current_speed = 30.0
        self.brake_phase = "braking"
        self.active_target_id = None

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
        prize_label = self.prize_var.get().strip()
        if not prize_label:
            return
        if hasattr(self, "_play_round_music"):
            self._play_round_music()
        if not self.wheel_names:
            self._prepare_wheel()
            if not self.wheel_names:
                messagebox.showinfo("提示", "当前奖项已无候选人")
                return
        prize_id = prize_label.split(" - ", 1)[0]
        prize = next((p for p in self.prizes if p.prize_id == prize_id), None)
        if not prize:
            messagebox.showinfo("提示", "当前奖项已无候选人")
            return

        clean_excluded_ids = set()
        for item in self.excluded_ids:
            if hasattr(item, "person_id"):
                clean_excluded_ids.add(str(item.person_id))
            else:
                clean_excluded_ids.add(str(item))

        remaining = remaining_slots(prize, self.lottery_state)
        if remaining <= 0:
            return

        preview_state = copy.deepcopy(self.lottery_state)
        # Bug2: 一次性抽完当前奖项剩余名额，进入自动连抽队列
        try:
            winners = draw_prize(
                prize,
                self.people,
                preview_state,
                self.global_must_win,
                clean_excluded_ids,
                include_excluded=self.include_excluded,
                excluded_winner_range=self.excluded_winner_range,
                prizes=self.prizes,
                draw_count=1,
            )
        except ValueError as exc:
            self.phase = "idle"
            messagebox.showinfo("结果", str(exc))
            return

        if not winners:
            self.phase = "idle"
            messagebox.showinfo("结果", "未能抽出中奖者。")
            return

        self.pending_winners = [] 
        self.target_queue = []

        for winner in winners:
            target_id = str(winner["person_id"])
            target_idx = next((item["index"] for item in self.wheel_names if str(item["id"]) == str(target_id)), -1)
            if target_idx != -1:
                self.pending_winners.append(winner)
                self.target_queue.append(target_id)

        if not self.target_queue:
            self.phase = "idle"
            self.result_var.set("无目标")
            self._update_btn_state()

    def _prepare_wheel(self) -> None:
        if self._all_prizes_complete():
            self._render_grand_summary()
            return
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
        prize_state = self.lottery_state.get("prizes", {}).get(prize_id, {"winners": []})
        existing_prize_winners = {str(pid) for pid in prize_state.get("winners", [])}
        previous_winners_set = {str(w["person_id"]) for w in self.lottery_state["winners"]} if prize.exclude_previous_winners else set()
        clean_excluded_ids = set()
        for item in self.excluded_ids:
            if hasattr(item, "person_id"):
                clean_excluded_ids.add(str(item.person_id))
            else:
                clean_excluded_ids.add(str(item))
        exclude_excluded_list = prize.exclude_excluded_list and not self.include_excluded

        blacklist = excluded_must_win | previous_winners_set | existing_prize_winners
        if exclude_excluded_list:
            blacklist |= clean_excluded_ids
        
        eligible = []
        for p in self.people:
            if str(p.person_id) not in blacklist: eligible.append(p)

        if not eligible:
            self.wheel_names = []
            self.result_var.set("无候选人")
            self.winner_listbox.delete(0, tk.END)
            self._request_render(force=True)
            return

        random.shuffle(eligible)
        
        total = len(eligible)
        self.segment_angle = 360.0 / total
        self.wheel_names = []
        random_colors = copy.copy(self.colors["wheel_colors"])
        
        for i, person in enumerate(eligible):
            dept = getattr(person, 'department', '')
            full_text = f"{dept} {person.person_id} {person.name}".strip()
            angle_center = i * self.segment_angle + self.segment_angle / 2
            self.wheel_names.append({
                "index": i,
                "id": str(person.person_id),
                "name": person.name,
                "full_text": full_text,
                "color": random_colors[i % len(random_colors)],
                "angle_center": angle_center,
                "angle_center_rad": math.radians(angle_center),
            })

        self.phase = "idle"
        self.wheel_rotation = 0.0 
        self.result_var.set(f"就绪 | {prize.name}")
        self.winner_listbox.delete(0, tk.END)
        self.revealed_winners = []
        self._update_btn_state()
        self._request_render(force=True)

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
        
        elif self.phase == "announcing":
            if self.anim_frame % 5 == 0:
                self._create_firework()
            if self.tts_done_event.is_set():
                self._begin_removal_after_announcement()
        elif self.phase == "auto_wait":
            if self.anim_frame % 5 == 0: self._create_firework()
            
            if self.tts_playing:
                self.auto_wait_start_time = current_time
            elif current_time - self.auto_wait_start_time > self.auto_wait_duration:
                if self.target_queue:
                    #self._reset_round_display()
                    self.phase = "spinning"
                    self._init_time_physics(self.locked_charge)
                    self.result_var.set("自动连抽中...")
                    self._update_btn_state()
                else:
                    if self._ensure_auto_queue():
                        #self._reset_round_display()
                        self.phase = "spinning"
                        self._init_time_physics(self.locked_charge)
                        self.result_var.set("自动连抽中...")
                        self._update_btn_state()
                    else:
                        self._show_prize_summary_if_complete()
        elif self.phase == "removing":
            self.removal_scale -= 0.1
            if self.removal_scale <= 0:
                self._finalize_removal()
            self._animate_removal_particles()
        elif self.phase == "announce":
            if not self.tts_playing:
                self._start_removal_from_pending()
        else:
            self._animate_removal_particles()

        resizing_recently = current_time - self._last_resize_event < 0.2
        if not resizing_recently or (current_time - self.last_render_time) >= 0.033:
            self._request_render(display_energy)
        self.draw_after_id = self.after(20, self._animate)

    def _calculate_stop_path_by_time(self):
        if not self.target_queue:
            return
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
        
        avg_speed = 6.0 
        estimated_dist = avg_speed * (self.brake_duration * 50) 
        
        extra_spins = math.ceil(estimated_dist / 360) * 360
        
        self.target_rotation = current_abs + rotation_needed + extra_spins
        self.decel_factor = 0.04 
    def _reset_round_display(self) -> None:
        self.winner_listbox.delete(0, tk.END)
        self.revealed_winners = []
        self.canvas.delete("fx_firework")
        
    def _speak_winner(self, department: str, person_id: str, name: str, prize_label: str) -> None:
        if not TTS_AVAILABLE:
            self.tts_playing = False
            self.tts_done_event.set()
            return
        self.tts_done_event.clear()
        self.tts_playing = True

        def _speak():
            engine = None
            try:
                with self.tts_lock:
                    engine = pyttsx3.init()
                    voices = engine.getProperty('voices')
                
                    # 语音优化：优先寻找更自然的中文女声
                    preferred_voices = ["YAOYAO", "HUIHUI", "XIAOXIAO", "ZH-CN"]
                    selected_voice = None
                    for pref in preferred_voices:
                        for v in voices:
                            if pref in v.name.upper() or pref in v.id.upper():
                                selected_voice = v.id
                                break
                        if selected_voice: break
                    
                    if selected_voice:
                        engine.setProperty('voice', selected_voice)
                    
                    # 慢速清晰播报：恭喜 + 工号 + 姓名 + 奖项
                    engine.setProperty('rate', 150)
                    spaced_id = " ，".join(str(person_id))
                    full_sentence = f"恭喜。{spaced_id}，{name}，获得{prize_label}"
                    engine.say(full_sentence)
                    
                    engine.runAndWait()
            except Exception as e:
                print("TTS error:", e)
            finally:
                if engine:
                    engine.stop()
                self.tts_playing = False
                self.tts_done_event.set()

        threading.Thread(target=_speak, daemon=True).start()

    def _handle_stop(self):
        if not self.target_queue: return
        self.active_target_id = None
        winner_id = str(self.target_queue.pop(0))
        winner_data = next((entry for entry in self.wheel_names if str(entry["id"]) == winner_id), None)
        if not winner_data:
            return
        info = winner_data['full_text']
        winner_entry = self.pending_winners.pop(0) if self.pending_winners else None
        if getattr(self, "single_round_display", False):
            self.revealed_winners = []
            self.winner_listbox.delete(0, tk.END)
        self.revealed_winners.append(info)
        self.winner_listbox.insert(tk.END, f"🏆 {info}")
        self.winner_listbox.see(tk.END) 
        
        if winner_entry:
            self._apply_winner_to_state(winner_entry)
            if self.on_transfer:
                self.on_transfer(self.lottery_state, [winner_entry])
        
        # 获取纯净奖项名称用于播报
        try:
            prize_full = self.prize_var.get()
            prize_label = prize_full.split(" - ")[1].split(" (")[0]
        except:
            prize_label = "奖品"

        # Bug3: 先播报，播报结束后再进入 removing 动画
        self._speak_winner("", winner_data.get("id", ""), winner_data.get("name", ""), prize_label)
        self.pending_removal_data = winner_data
        self.pending_removal_idx = winner_data.get("index", -1)

        # 核心修复：如果是最后一个人，先进入 removing 状态，等 finalize_removal 再处理结算
        current_prize = self._get_current_prize()
        remaining = remaining_slots(current_prize, self.lottery_state) if current_prize else 0
        if remaining <= 0 and not self.target_queue:
            self.post_removal_phase = "prize_summary"
        else:
            self.post_removal_phase = "auto_wait"
            
        self.phase = "announcing"
        self.result_var.set("🎙️ 正在播报中奖结果...")
        self._update_btn_state()

    def _apply_winner_to_state(self, winner: dict[str, Any]) -> None:
        if not winner:
            return
        prize_state = self.lottery_state.setdefault("prizes", {}).setdefault(winner["prize_id"], {"winners": []})
        winner_id = str(winner["person_id"])
        if winner_id not in {str(pid) for pid in prize_state["winners"]}:
            prize_state["winners"].append(winner_id)
        self.lottery_state.setdefault("winners", []).append(winner)

    def _start_removal_from_pending(self) -> None:
        if self.pending_removal_data and self.pending_removal_idx >= 0:
            self.removing_idx = self.pending_removal_idx
            self.removal_scale = 1.0
            self._spawn_removal_particles(self.pending_removal_data)
            self.phase = "removing"
            self._update_btn_state()
        else:
            self._complete_post_removal_phase()

    def _begin_removal_after_announcement(self) -> None:
        """播报结束后进入 removing 动画或直接进入下一阶段。"""
        winner_data = self.pending_removal_data
        if not winner_data:
            self._complete_post_removal_phase()
            return
        current_prize = self._get_current_prize()
        should_remove = bool(current_prize and current_prize.exclude_previous_winners)
        if should_remove:
            self.removing_idx = self.pending_removal_idx
            self.removal_scale = 1.0
            self._spawn_removal_particles(winner_data)
            self.phase = "removing"
            self._update_btn_state()
        else:
            self._complete_post_removal_phase()

    def _complete_post_removal_phase(self) -> None:
        if self.post_removal_phase == "prize_summary":
            self.post_removal_phase = None
            self._show_prize_summary_if_complete()
            return
        if self.post_removal_phase == "auto_wait":
            self.post_removal_phase = None
            self.phase = "auto_wait"
            self._update_btn_state()
            return
        self.post_removal_phase = None

    def _finalize_removal(self) -> None:
        if 0 <= self.removing_idx < len(self.wheel_names):
            removed_item = self.wheel_names.pop(self.removing_idx)
            arc_id = removed_item.get("arc_id")
            if arc_id:
                self.canvas.delete(arc_id)
            text_ids = removed_item.get("text_ids") or []
            for t_id in text_ids:
                self.canvas.delete(t_id)
            self._rebuild_wheel_layout()
        self.pending_removal_data = None
        self.pending_removal_idx = -1
        self.removing_idx = -1
        self.removal_scale = 1.0
        self._complete_post_removal_phase()

    def _rebuild_wheel_layout(self) -> None:
        if self.wheel_names:
            self.segment_angle = 360.0 / len(self.wheel_names)
            for i, item in enumerate(self.wheel_names):
                item["index"] = i
                angle_center = i * self.segment_angle + self.segment_angle / 2
                item["angle_center"] = angle_center
                # 性能优化(缓存)：同步更新中心角弧度
                item["angle_center_rad"] = math.radians(angle_center)
        else:
            self.segment_angle = 0.0
