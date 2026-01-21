#!/usr/bin/env python3
"""Rendering helpers for the wheel window."""

from __future__ import annotations

import math
import random
import time
import tkinter as tk


class WheelWindowRender:
    # ---------------- 渲染 ----------------
    def _create_firework(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        x = random.randint(50, width-50)
        y = random.randint(50, height-50)
        color = random.choice(self.colors["wheel_colors"])
        size = random.randint(5, 15)
        self.canvas.create_oval(x, y, x+size, y+size, fill=color, tags="fx_firework")
        self.root.after(500, lambda: self.canvas.delete("fx_firework"))

    def _draw_text_with_outline(self, x, y, text, font, text_color, outline_color, thickness=2, tags=None, justify=tk.CENTER, angle=0):
        for dx in range(-thickness, thickness+1):
            for dy in range(-thickness, thickness+1):
                if dx == 0 and dy == 0: continue
                self.canvas.create_text(
                    x + dx,
                    y + dy,
                    text=text,
                    font=font,
                    fill=outline_color,
                    tags=tags,
                    justify=justify,
                    angle=angle,
                )
        self.canvas.create_text(x, y, text=text, font=font, fill=text_color, tags=tags, justify=justify, angle=angle)

    def _angle_distance(self, a: float, b: float) -> float:
        diff = abs((a - b) % 360)
        return min(diff, 360 - diff)

    def _request_render(self, display_energy: float | None = None, force: bool = False) -> None:
        """性能优化(Throttling)：渲染请求合并到固定帧率。"""
        if display_energy is not None:
            self.pending_display_energy = display_energy
        if force:
            self.force_full_render = True
        if self.render_after_id:
            return
        self.render_after_id = self.after(self.render_interval_ms, self._render_wheel_throttled)

    def _render_wheel_throttled(self) -> None:
        now = time.monotonic()
        min_interval = 0.033
        elapsed = now - self.last_render_time
        if elapsed < min_interval:
            remaining = int((min_interval - elapsed) * 1000)
            self.render_after_id = self.after(max(1, remaining), self._render_wheel_throttled)
            return
        self.render_after_id = None
        self._render_wheel(self.pending_display_energy, force_full=self.force_full_render, now=now)
        self.force_full_render = False

    def _clear_canvas_layers(self) -> None:
        self.canvas.delete(
            "bg",
            "wheel",
            "text",
            "overlay",
            "fx_particles",
            "fx_firework",
            "summary_items",
            "summary_bg",
            "summary_text",
            "prize_summary",
        )

# ---------------- 渲染 (修复版) ----------------
    def _render_wheel(self, display_energy=0.0, force_full: bool = False, now: float | None = None) -> None:
        if self.phase in ["summary", "prize_summary"]: return 

        if now is None:
            now = time.monotonic()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            return

        # 检测画布尺寸变化，如果变化则强制全量重绘
        size_changed = (width, height) != self.last_canvas_size
        if size_changed:
            self.last_canvas_size = (width, height)
            force_full = True

        # --- 1. 背景层 (BG) ---
        # 仅在需要时重绘背景，减少开销
        if force_full or now - self.last_bg_render_time >= self.bg_update_interval:
            self.canvas.delete("bg")
            for p in self.bg_particles:
                px = p["x"] * width
                py = p["y"] * height
                r = p["size"]
                self.canvas.create_oval(
                    px, py, px + r, py + r,
                    fill=p["color"], outline="", tags="bg",
                )
            self.last_bg_render_time = now

        # 如果是强制重绘（如Resize），清理所有动态元素并重置ID缓存
        if force_full:
            self.canvas.delete("wheel")
            self.canvas.delete("text")
            self.canvas.delete("overlay")
            self.canvas.delete("fx_particles")
            # 清除 Python 对象中存储的 ID，确保重新创建
            for item in self.wheel_names:
                item["arc_id"] = None
                item["text_ids"] = None

        # --- 计算中心点 ---
        top_margin = 150
        max_diameter = min(width - 40, height - top_margin - 50)
        radius = max_diameter / 2
        cx = width / 2
        cy = top_margin + radius 
        
        if not self.wheel_names:
            self.canvas.delete("text") # 清理旧文本
            self.canvas.create_text(
                cx, cy, text="暂无数据", fill=self.colors["text_muted"],
                font=("Microsoft YaHei UI", 20), tags="text",
            )
            self.last_render_time = now
            return

        # --- 字体大小计算 ---
        total_names = len(self.wheel_names)
        if total_names >= 160: base_font_size = 6
        elif total_names >= 120: base_font_size = 8
        elif total_names >= 100: base_font_size = 10
        elif total_names >= 80: base_font_size = 12
        else: base_font_size = 14
        
        rotation_mod = self.wheel_rotation % 360
        rotation_rad = math.radians(rotation_mod)
        pointer_text_top = ""
        
        # --- 2. 绘制/更新 转盘扇区 (Wheel) 和 名字 (Text) ---
        # 关键修改：不再每帧 delete("wheel") 和 delete("text")
        
        for item in self.wheel_names:
            # A. 计算角度
            segment_extent = self.segment_angle
            segment_half = self.segment_angle / 2
            
            # 处理“移除中”的动画效果
            if self.phase == "removing" and item["index"] == self.removing_idx:
                segment_extent = self.segment_angle * max(0.0, self.removal_scale)
                segment_half = segment_extent / 2
            
            start_angle = (item["angle_center"] - segment_half + rotation_mod) % 360
            
            # B. 绘制或更新扇区 (Arc)
            arc_id = item.get("arc_id")
            if not arc_id:
                # 如果ID不存在（第一次渲染或被force_full清除），则创建
                if segment_extent > 0.1:
                    item["arc_id"] = self.canvas.create_arc(
                        cx - radius, cy - radius, cx + radius, cy + radius,
                        start=start_angle, extent=segment_extent,
                        fill=item["color"], outline=item["color"], width=1,
                        tags="wheel"
                    )
            else:
                # 如果ID存在，直接更新属性（消除闪烁的关键）
                if segment_extent > 0.1:
                    try:
                        self.canvas.itemconfigure(
                            arc_id, 
                            start=start_angle, 
                            extent=segment_extent,
                            state="normal" # 确保可见
                        )
                        self.canvas.coords(
                            arc_id, 
                            cx - radius, cy - radius, cx + radius, cy + radius
                        )
                    except Exception:
                        # 如果canvas被意外清空导致ID失效，重新创建
                        item["arc_id"] = None 
                else:
                    # 扇区太小或隐藏时
                    self.canvas.itemconfigure(arc_id, state="hidden")

            # C. 指针检测逻辑
            mid_angle = (item["angle_center"] + rotation_mod) % 360
            dist_to_pointer = self._angle_distance(mid_angle, 90)
            if dist_to_pointer < self.segment_angle / 2:
                pointer_text_top = item["full_text"]

                

            # D. 绘制或更新 名字 (Text)
            # 始终使用高性能模式：每个字符一个对象，更新位置而不是删除重建
            mid_angle_rad = item["angle_center_rad"] + rotation_rad
            name_chars = item.get("name_chars", [item["name"]])
            base_radius = radius * 0.82
            char_step = min(12.0, radius * 0.04)
            
            # 文字角度修正，防止倒立
            text_angle = mid_angle
            if 90 < mid_angle < 270:
                text_angle += 180
            
            text_ids = item.get("text_ids")
            
            # 如果字符数量变化或ID丢失，需要重建
            if not text_ids or len(text_ids) != len(name_chars):
                # 清理旧的（如果有）
                if text_ids:
                    for tid in text_ids: self.canvas.delete(tid)
                
                new_ids = []
                for char in name_chars:
                    new_ids.append(self.canvas.create_text(
                        0, 0, text=char,
                        font=("Microsoft YaHei UI", base_font_size, "bold"),
                        fill=self.colors["white"],
                        tags="text", justify=tk.CENTER
                    ))
                item["text_ids"] = new_ids
                text_ids = new_ids

            # 更新所有字符的位置和角度
            for char_index, (char, t_id) in enumerate(zip(name_chars, text_ids)):
                if self.phase == "removing" and item["index"] == self.removing_idx and segment_extent <= 0.1:
                    self.canvas.itemconfigure(t_id, state="hidden")
                    continue
                text_radius = base_radius + char_index * char_step
                tx = cx + text_radius * math.cos(mid_angle_rad)
                ty = cy - text_radius * math.sin(mid_angle_rad)
                
                try:
                    self.canvas.coords(t_id, tx, ty)
                    self.canvas.itemconfigure(
                        t_id, 
                        angle=text_angle, 
                        text=char, # 确保文字内容正确
                        font=("Microsoft YaHei UI", base_font_size, "bold"),
                        state="normal"
                    )
                except Exception:
                    item["text_ids"] = None # ID失效，下帧重建

        # 确保文字层在扇区层之上
        self.canvas.tag_raise("text", "wheel")

        # --- 3. 覆盖层 (Overlay) ---
        # 覆盖层元素较少，可以使用删除重建的方式，或者也优化为 update
        # 这里为了保险起见，覆盖层我们每帧重建（因为形状简单），但要确保在最上层
        self.canvas.delete("overlay") 
        
        # 中心圆
        self.canvas.create_oval(
            cx - 70, cy - 70, cx + 70, cy + 70,
            fill=self.colors["white"], outline=self.colors["gold"],
            width=4, tags="overlay",
        )
        
        # 中心文字
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
        
        # 使用普通 text 绘制中心文字（避免 _draw_text_with_outline 造成的性能负担）
        self.canvas.create_text(
            cx, cy - 10, text=center_text_big,
            font=("Microsoft YaHei UI", 24, "bold"), fill=self.colors["red"],
            tags="overlay"
        )
        self.canvas.create_text(
            cx, cy + 25, text=center_text_small,
            font=("Microsoft YaHei UI", 12, "bold"), fill=self.colors["text_muted"],
            tags="overlay",
        )

        # 顶部指针
        self.canvas.create_polygon(
            cx, cy - radius + 50,
            cx - 15, cy - radius + 10,
            cx + 15, cy - radius + 10,
            fill=self.colors["red"], outline="white", width=2,
            tags="overlay",
        )
        
        # 选中人名高亮框
        if pointer_text_top:
            bg_rect_y = cy - radius - 80
            self.canvas.create_rectangle(
                cx - 250, bg_rect_y, cx + 250, bg_rect_y + 60,
                fill="#7A1616", outline=self.colors["gold_deep"], width=2,
                tags="overlay",
            )
            self.canvas.create_text(
                cx, bg_rect_y + 30, text=pointer_text_top,
                font=("Microsoft YaHei UI", 24, "bold"), fill=self.colors["gold"],
                tags="overlay",
            )

        # 粒子特效更新 (保持原逻辑，只需确保不被删除)
        self._render_removal_particles()

        # 能量条绘制
        if self.phase != "finished":
            bar_w = 40
            bar_max_h = 400
            bar_x = width - 60 
            bar_bottom_y = height - 50 
            
            # 能量槽背景
            self.canvas.create_rectangle(
                bar_x, bar_bottom_y - bar_max_h, bar_x + bar_w, bar_bottom_y,
                outline=self.colors["panel_border"], width=2,
                fill=self.colors["red_deep"], tags="overlay",
            )
            
            fill_h = bar_max_h * display_energy
            fill_h = max(0, fill_h)
            fill_top_y = bar_bottom_y - fill_h
            
            if display_energy > 0.7: bar_color = self.colors["red"] 
            elif display_energy > 0.3: bar_color = self.colors["gold"]
            else: bar_color = self.colors["gold_deep"]
            
            self.canvas.create_rectangle(
                bar_x, fill_top_y, bar_x + bar_w, bar_bottom_y,
                fill=bar_color, outline="", tags="overlay",
            )
            
            if self.phase == "charging":
                self.canvas.create_text(
                    bar_x - 15, fill_top_y, text=self.encouragement_text,
                    fill="white", font=("Microsoft YaHei UI", 16, "bold"),
                    anchor="e", tags="overlay",
                )
            
            self.canvas.create_text(
                bar_x + bar_w / 2, bar_bottom_y + 25, text="动能",
                fill=self.colors["text_muted"], font=("Microsoft YaHei UI", 9),
                tags="overlay",
            )
        
        self.last_render_time = now
        
    def _format_names_rows(self, names: list[str], per_row: int = 4) -> str:
        if not names:
            return ""
        rows = []
        for i in range(0, len(names), per_row):
            rows.append("  ".join(names[i:i + per_row]))
        return "\n".join(rows)

    def _render_grand_summary(self):
        self.phase = "summary"
        if hasattr(self, "_play_summary_music"):
            self._play_summary_music()
        self.result_var.set("🎉 所有奖项抽取完毕！")
        self._clear_canvas_layers()
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_rectangle(0, 0, width, height, fill=self.colors["bg_canvas"], outline="", tags="summary_bg")
        
        self.canvas.create_text(width/2, 100, text="🏆 中奖总榜 🏆", font=("Microsoft YaHei UI", 36, "bold"), fill=self.colors["gold"], tags="summary_text")

        y_start = 180
        winners = self.lottery_state.get("winners", [])
        
        grouped = {}
        for w in winners:
            p_name = w.get('prize_name', '未知奖项')
            if p_name not in grouped: grouped[p_name] = []
            grouped[p_name].append(w.get('person_name'))

        ordered_prizes = []
        seen_prize_names = set()
        for prize in self.prizes:
            if prize.name in grouped and prize.name not in seen_prize_names:
                ordered_prizes.append((prize.name, grouped[prize.name]))
                seen_prize_names.add(prize.name)
        for prize_name, names in grouped.items():
            if prize_name not in seen_prize_names:
                ordered_prizes.append((prize_name, names))
                seen_prize_names.add(prize_name)

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
                fill=self.colors["gold_deep"],
                anchor="n",
                tags="summary_items",
            )
            names_text = self._format_names_rows(names) if names else "暂无"
            self.canvas.create_text(
                x,
                y + header_height,
                text=names_text,
                font=("Microsoft YaHei UI", 14),
                fill=self.colors["white"],
                anchor="n",
                tags="summary_items",
            )
            names_lines = max(1, len(names_text.splitlines()))
            block_height = header_height + names_lines * line_height + block_gap
            column_heights[col] += block_height

        self._start_summary_scroll(max(column_heights), height)

    def _render_prize_summary(self, prize) -> None:
        self._clear_canvas_layers()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_rectangle(0, 0, width, height, fill=self.colors["bg_canvas"], outline="", tags="prize_summary")

        title_text = f"🎉 {prize.name} 中奖结果"
        self.canvas.create_text(width / 2, 90, text=title_text, font=("Microsoft YaHei UI", 32, "bold"), fill=self.colors["gold"], tags="prize_summary")

        winners = [
            winner for winner in self.lottery_state.get("winners", [])
            if winner.get("prize_id") == prize.prize_id
        ]
        names = [winner.get("person_name", "未知") for winner in winners]
        if not names:
            self.canvas.create_text(width / 2, height / 2, text="暂无中奖者", font=("Microsoft YaHei UI", 22, "bold"), fill=self.colors["white"], tags="prize_summary")
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
                fill=self.colors["white"],
                anchor="n",
                justify=tk.LEFT,
                tags="prize_summary",
            )
