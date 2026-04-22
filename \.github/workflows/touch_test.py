# -*- coding: utf-8 -*-
"""
触控点击灵敏度测试工具
支持: 鼠标点击 + 触控笔/手指触摸
Win7 32位 + Win10 兼容

触控保持检测:
  - 按压时长实时计数
  - 位置漂移检测（持续按压时手指微小移动）
  - 触控压力值（如果有）
  - 松手后记录完整数据
"""

import sys
import time
import math
import tkinter as tk
from tkinter import font as tkfont

# ============================================================
# 配置
# ============================================================
BG_COLOR = "#1a1a2e"
PANEL_BG = "#16213e"
ACCENT = "#00d2ff"
ACCENT2 = "#ff6b6b"
SUCCESS = "#4ecca3"
WARN = "#ffd93d"
TEXT_COLOR = "#e0e0e0"
DIM_TEXT = "#888888"

# 触控保持阈值
MOVE_THRESHOLD = 5  # 像素，超过视为移动
HOLD_INTERVAL = 50  # ms，长按刷新间隔

# ============================================================
# 主程序
# ============================================================
class TouchTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("触控灵敏度测试")
        self.root.configure(bg=BG_COLOR)

        # 自动全屏（覆盖任务栏）
        self.root.attributes("-fullscreen", True)

        # 状态
        self.touch_active = False
        self.touch_start_time = 0
        self.touch_start_x = 0
        self.touch_start_y = 0
        self.last_x = 0
        self.last_y = 0
        self.hold_job = None
        self.click_count = 0
        self.hold_count = 0
        self.drift_total = 0
        self.drift_max = 0

        # 历史记录（用于统计）
        self.latencies = []
        self.hold_durations = []

        # 动画效果
        self.rings = []  # [(x, y, radius, alpha, start_time)]

        self._build_ui()

        # 键盘退出
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<Key>", lambda e: self._on_key(e))

        # 触控/鼠标事件（绑定到全屏 Canvas）
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        # 触摸事件（支持触控设备）
        self.canvas.bind("<TouchBegin>", self._on_touch_begin)
        self.canvas.bind("<TouchEnd>", self._on_touch_end)
        self.canvas.bind("<TouchMove>", self._on_touch_move)

        # 双击全屏切换
        self.root.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        self._update_rings()

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        self.canvas = tk.Canvas(
            self.root,
            bg=BG_COLOR,
            highlightthickness=0,
            cursor="crosshair"
        )
        self.canvas.pack(fill="both", expand=True)

        # 信息面板（顶部）
        self.info_frame = tk.Frame(self.canvas, bg=PANEL_BG, bd=0)
        self.info_frame.place(x=0, y=0, relwidth=1, height=90)

        self._build_info_bar()

        # 右侧状态面板
        self.side_panel = tk.Frame(self.canvas, bg=PANEL_BG, bd=0)
        self.side_panel.place(relx=1, y=0, width=280, relheight=1)

        # 左下角模式切换
        self.mode_btn = tk.Button(
            self.canvas,
            text="[ 双击切换全屏 ]  [ ESC 退出 ]",
            bg=PANEL_BG,
            fg=DIM_TEXT,
            font=("Consolas", 10),
            bd=0,
            padx=10,
            pady=5,
            anchor="sw",
            command=self._toggle_fullscreen
        )
        self.mode_btn.place(relx=0, rely=1, anchor="sw", x=10, y=-10)

        # 初始提示文字
        self.canvas.create_text(
            self.canvas.winfo_reqwidth() / 2,
            self.canvas.winfo_reqheight() / 2,
            text="点击或触摸屏幕开始测试",
            fill=DIM_TEXT,
            font=("Microsoft YaHei", 24),
            tags="hint"
        )

    def _build_info_bar(self):
        self.info_labels = {}
        items = [
            ("点击次数", "0"),
            ("长按次数", "0"),
            ("平均延迟", "-- ms"),
            ("最长延迟", "-- ms"),
            ("平均按压时长", "-- ms"),
            ("最大漂移", "-- px"),
        ]
        x = 20
        for i, (name, val) in enumerate(items):
            fw = tk.Frame(self.info_frame, bg=PANEL_BG)
            fw.place(x=x, y=10, width=160, height=70)

            tk.Label(
                fw, text=name,
                bg=PANEL_BG, fg=DIM_TEXT,
                font=("Microsoft YaHei", 10)
            ).pack(anchor="w", y=(8 if i == 0 else 5))

            lbl = tk.Label(
                fw, text=val,
                bg=PANEL_BG, fg=ACCENT,
                font=("Consolas", 18, "bold")
            )
            lbl.pack(anchor="w")
            self.info_labels[name] = lbl
            x += 170

    def _update_side_panel(self):
        # 清空旧面板
        for w in self.side_panel.winfo_children():
            w.destroy()

        records = list(reversed(self.latencies[-20:]))
        tk.Label(
            self.side_panel, text="最近 20 次点击记录",
            bg=PANEL_BG, fg=DIM_TEXT,
            font=("Microsoft YaHei", 11)
        ).place(x=10, y=10)

        y = 38
        for i, lat in enumerate(records):
            color = SUCCESS if lat < 50 else (WARN if lat < 100 else ACCENT2)
            tk.Label(
                self.side_panel,
                text=f"#{i+1}: {lat:.1f} ms",
                bg=PANEL_BG, fg=color,
                font=("Consolas", 10)
            ).place(x=15, y=y)
            y += 20

        # 长按记录
        tk.Label(
            self.side_panel, text="最近 10 次长按记录",
            bg=PANEL_BG, fg=DIM_TEXT,
            font=("Microsoft YaHei", 11)
        ).place(x=10, y=y + 10)

        y += 40
        holds = list(reversed(self.hold_durations[-10:]))
        for i, dur in enumerate(holds):
            tk.Label(
                self.side_panel,
                text=f"#{i+1}: {dur:.0f} ms",
                bg=PANEL_BG, fg=ACCENT,
                font=("Consolas", 10)
            ).place(x=15, y=y)
            y += 20

    # --------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------
    def _on_press(self, event):
        self._touch_down(event.x, event.y, event.time)

    def _on_release(self, event):
        self._touch_up(event.x, event.y, event.time)

    def _on_drag(self, event):
        self._touch_move(event.x, event.y)

    def _on_touch_begin(self, event):
        x = event.x
        y = event.y
        self._touch_down(x, y, 0)

    def _on_touch_end(self, event):
        x = event.x if hasattr(event, 'x') else self.last_x
        y = event.y if hasattr(event, 'y') else self.last_y
        self._touch_up(x, y, 0)

    def _on_touch_move(self, event):
        x = event.x
        y = event.y
        self._touch_move(x, y)

    def _on_key(self, event):
        if event.keysym == "Escape":
            self.root.destroy()

    def _toggle_fullscreen(self):
        state = not self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", state)

    # --------------------------------------------------------
    # 核心逻辑
    # --------------------------------------------------------
    def _touch_down(self, x, y, timestamp):
        # 去除初始提示
        self.canvas.delete("hint")

        now = time.time()
        self.touch_active = True
        self.touch_start_time = now
        self.touch_start_x = x
        self.touch_start_y = y
        self.last_x = x
        self.last_y = y
        self._drift = 0

        # 计算延迟（如果有时间戳）
        if timestamp > 0:
            latency_ms = (now * 1000) - timestamp
        else:
            latency_ms = 0

        self.click_count += 1
        self._show_ring(x, y, latency_ms)

        # 清除旧的 hold 更新
        if self.hold_job:
            self.root.after_cancel(self.hold_job)

        # 开始 hold 刷新
        self._start_hold_loop(x, y)

        self._update_info()
        self._update_side_panel()

    def _touch_up(self, x, y, timestamp):
        if not self.touch_active:
            return

        duration_ms = (time.time() - self.touch_start_time) * 1000
        self.touch_active = False

        if self.hold_job:
            self.root.after_cancel(self.hold_job)
            self.hold_job = None

        # 计算漂移
        drift = math.sqrt(
            (x - self.touch_start_x)**2 + (y - self.touch_start_y)**2
        )

        is_long_press = duration_ms >= 500

        if is_long_press:
            self.hold_count += 1
            self.hold_durations.append(duration_ms)
            color = WARN
            tag = f"lp_{self.hold_count}"
            self.canvas.create_text(
                x, y - 50,
                text=f"长按 {duration_ms:.0f}ms | 漂移 {drift:.1f}px",
                fill=WARN,
                font=("Consolas", 12, "bold"),
                tags=tag
            )
            self.root.after(2000, lambda: self.canvas.delete(tag))

        self._update_info()
        self._update_side_panel()

    def _touch_move(self, x, y):
        if not self.touch_active:
            return
        self.last_x = x
        self.last_y = y

        # 漂移检测
        drift = math.sqrt(
            (x - self.touch_start_x)**2 + (y - self.touch_start_y)**2
        )
        self._drift = drift
        if drift > self.drift_max:
            self.drift_max = drift

    def _start_hold_loop(self, start_x, start_y):
        """持续按压时，每 HOLD_INTERVAL ms 更新一次显示"""
        if not self.touch_active:
            return

        elapsed_ms = (time.time() - self.touch_start_time) * 1000
        drift = self._drift if hasattr(self, '_drift') else 0

        # 显示按压状态
        tag = "hold_indicator"
        self.canvas.delete(tag)

        # 颜色随按压时长变化
        if elapsed_ms < 500:
            color = ACCENT
        elif elapsed_ms < 2000:
            color = WARN
        else:
            color = ACCENT2

        self.canvas.create_text(
            start_x, start_y - 35,
            text=f"按压中... {elapsed_ms:.0f}ms | 漂移 {drift:.1f}px",
            fill=color,
            font=("Consolas", 13, "bold"),
            tags=tag
        )

        self.hold_job = self.root.after(HOLD_INTERVAL, lambda: self._start_hold_loop(start_x, start_y))

    # --------------------------------------------------------
    # 视觉效果
    # --------------------------------------------------------
    def _show_ring(self, x, y, latency):
        # 圆圈扩散动画
        color = SUCCESS if latency < 50 else (WARN if latency < 100 else ACCENT2)
        ring = self.canvas.create_oval(
            x - 5, y - 5, x + 5, y + 5,
            outline=color, width=2, tags="ring"
        )
        self.rings.append({
            "id": ring,
            "x": x, "y": y,
            "r": 5,
            "color": color,
            "alpha": 1.0,
            "start": time.time()
        })

        # 显示坐标和延迟
        tag = f"coord_{time.time()}"
        self.canvas.create_text(
            x + 15, y - 15,
            text=f"+{x},{y}  {latency:.0f}ms",
            fill=color,
            font=("Consolas", 11),
            tags=tag
        )
        self.root.after(3000, lambda: self.canvas.delete(tag))

    def _update_rings(self):
        """动画循环"""
        to_delete = []
        for ring in self.rings:
            age = time.time() - ring["start"]
            if age > 1.0:
                self.canvas.delete(ring["id"])
                to_delete.append(ring)
            else:
                expansion = age * 80  # 扩散速度
                new_r = 5 + expansion
                alpha = 1.0 - age
                x, y = ring["x"], ring["y"]
                self.canvas.coords(
                    ring["id"],
                    x - new_r, y - new_r, x + new_r, y + new_r
                )

        for r in to_delete:
            self.rings.remove(r)

        self.root.after(16, self._update_rings)  # ~60fps

    # --------------------------------------------------------
    # 信息更新
    # --------------------------------------------------------
    def _update_info(self):
        def set(name, val):
            if name in self.info_labels:
                self.info_labels[name].config(text=val)

        set("点击次数", str(self.click_count))
        set("长按次数", str(self.hold_count))

        if self.latencies:
            avg = sum(self.latencies) / len(self.latencies)
            mx = max(self.latencies)
            set("平均延迟", f"{avg:.1f} ms")
            set("最长延迟", f"{mx:.1f} ms")
        else:
            set("平均延迟", "-- ms")
            set("最长延迟", "-- ms")

        if self.hold_durations:
            avg_hold = sum(self.hold_durations) / len(self.hold_durations)
            set("平均按压时长", f"{avg_hold:.0f} ms")
        else:
            set("平均按压时长", "-- ms")

        set("最大漂移", f"{self.drift_max:.1f} px")


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    # 打印启动信息
    print("=" * 50)
    print("  触控灵敏度测试工具")
    print("  - 双击切换全屏/窗口")
    print("  - ESC 退出")
    print("  - 支持鼠标点击 + 触控屏幕")
    print("=" * 50)

    root = tk.Tk()
    app = TouchTestApp(root)
    root.mainloop()
