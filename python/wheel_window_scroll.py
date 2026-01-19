#!/usr/bin/env python3
"""Scrolling helpers for the wheel window."""

from __future__ import annotations


class WheelWindowScroll:
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
