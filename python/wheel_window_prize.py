#!/usr/bin/env python3
"""Prize flow helpers for the wheel window."""

from __future__ import annotations

from typing import Any

from lottery import remaining_slots


class WheelWindowPrize:
    def update_prizes(self, prizes: list[Any], state: dict[str, Any]) -> None:
        self.prizes = prizes
        self.lottery_state = state
        
        current_val = self.prize_var.get()
        current_id = current_val.split(" - ")[0] if current_val else None
        
        self._refresh_prize_options(hide_completed=False)
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

    def _get_current_prize(self):
        label = self.prize_var.get()
        if not label:
            return None
        prize_id = label.split(" - ", 1)[0]
        return next((prize for prize in self.prizes if prize.prize_id == prize_id), None)

    def _current_prize_remaining(self) -> int:
        current_prize = self._get_current_prize()
        if not current_prize:
            return 0
        return remaining_slots(current_prize, self.lottery_state)

    def _has_next_prize(self) -> bool:
        return self._next_available_prize() is not None

    def _all_prizes_complete(self) -> bool:
        return all(remaining_slots(prize, self.lottery_state) <= 0 for prize in self.prizes)

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
        target_option = next((opt for opt in options if opt.startswith(f"{next_prize.prize_id} - ")), None)
        if target_option:
            self.prize_var.set(target_option)
            self.phase = "idle"
            self.result_var.set("请长按空格/按钮蓄力，开始抽奖")
            self._prepare_wheel()

    def _is_current_prize_complete(self) -> bool:
        prize = self._get_current_prize()
        if not prize:
            return True
        return remaining_slots(prize, self.lottery_state) <= 0

    def _show_prize_summary_if_complete(self) -> None:
        if not self._is_current_prize_complete():
            return
        current_prize = self._get_current_prize()
        if not current_prize:
            return
        self.phase = "prize_summary"
        self.is_showing_prize_result = True
        self.result_var.set(f"🎉 {current_prize.name} 抽取完毕！点击确认继续")
        self._render_prize_summary(current_prize)
        self._update_btn_state()

    def _ensure_auto_queue(self) -> bool:
        if not self.target_queue:
            remaining = self._current_prize_remaining()
            if remaining > 0:
                self.result_var.set("准备下一轮抽奖...")
                self.phase = "idle"
                if not self.space_held:
                    return False
            else:
                self.result_var.set("当前奖项已抽完")
                self.phase = "prize_summary"
                self._show_prize_summary_if_complete()
                return False
        return True

    def _confirm_prize_result(self) -> None:
        """点击确认结算：仅关闭统计画面，不自动跳转下一奖项"""
        # Bug1: 若所有奖项名额都抽完，确认后直接进入总榜
        if self._all_prizes_complete():
            self.is_showing_prize_result = False
            self._render_grand_summary()
            self._update_btn_state()
            return
        self.is_showing_prize_result = False
        # 此时才根据需要刷新一次列表，把刚才抽完的奖项标记为 0
        self._refresh_prize_options(hide_completed=False)
        if not self._has_next_prize():
            self._render_grand_summary()
            self._update_btn_state()
            return
        self.phase = "idle"
        self.result_var.set("当前奖项已结束，请手动切换下一奖项")
        self._prepare_wheel() # 重新准备画布（显示空或就绪）
