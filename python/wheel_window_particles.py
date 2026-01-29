#!/usr/bin/env python3
"""Particle helpers for the wheel window."""

from __future__ import annotations

import math
import random
from typing import Any


class WheelWindowParticles:
    def _create_particle(self):
        return {
            "x": random.random(),
            "y": random.random(),
            "size": random.randint(1, 3),
            "speed": random.uniform(0.0003, 0.0015),
            "color": random.choice(["#FFF8E7", "#F4C542", "#E53935", "#B71C1C"]),
        }

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
        self.canvas.delete("fx_particles")
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
                tags="fx_particles",
            )
