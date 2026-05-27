import tkinter as tk
from tkinter import ttk
import math
import time
import threading
from PIL import Image, ImageDraw
import pystray

# ── Constants ──────────────────────────────────────
WORK_TIME = 25 * 60
SHORT_BREAK = 5 * 60
LONG_BREAK = 15 * 60

COLORS = {
    'bg': '#1a1b2e',
    'card': '#252745',
    'ring_bg': '#2d2f50',
    'work': '#ff6b6b',
    'short_break': '#51cf66',
    'long_break': '#339af0',
    'text': '#e9ecef',
    'muted': '#868e96',
    'btn_bg': '#2d2f50',
    'btn_hover': '#363864',
}


class PomodoroApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('番茄钟')
        self.root.geometry('420x580')
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS['bg'])

        # State
        self.mode = 'work'
        self.time_left = WORK_TIME
        self.total_time = WORK_TIME
        self.running = False
        self.timer_id = None
        self.completed = 0
        self.always_on_top = tk.BooleanVar(value=True)
        self.after_id = None
        self.tray_icon = None

        # Build UI
        self._build_ui()
        self._update_display()

        # System tray (after UI is ready)
        self._start_tray()

        # Window config
        self.root.attributes('-topmost', True)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # Keyboard
        self.root.bind('<space>', lambda e: self._toggle())
        self.root.bind('<Key-r>', lambda e: self._reset())
        self.root.bind('<Key-Right>', lambda e: self._skip())
        self.root.bind('<Key-1>', lambda e: self._set_mode('work'))
        self.root.bind('<Key-2>', lambda e: self._set_mode('short_break'))
        self.root.bind('<Key-3>', lambda e: self._set_mode('long_break'))

        # Center on screen
        self.root.update_idletasks()
        w, h = 420, 580
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f'{w}x{h}+{x}+{y}')

        self.root.mainloop()

    # ── UI Construction ────────────────────────────

    def _build_ui(self):
        main = tk.Frame(self.root, bg=COLORS['bg'])
        main.pack(fill='both', expand=True, padx=30, pady=25)

        # Title
        tk.Label(main, text='番茄钟', font=('Segoe UI', 11, 'bold'),
                 fg=COLORS['muted'], bg=COLORS['bg']).pack(pady=(0, 18))

        # Mode tabs
        tab_frame = tk.Frame(main, bg=COLORS['ring_bg'])
        tab_frame.pack(fill='x', pady=(0, 24))

        self.tab_btns = {}
        for key, label in [('work', '专注'), ('short_break', '小憩'), ('long_break', '长休')]:
            btn = tk.Button(
                tab_frame, text=label,
                font=('Segoe UI', 9, 'bold'),
                fg=COLORS['muted'], bg=COLORS['ring_bg'],
                activebackground=COLORS['btn_hover'],
                activeforeground=COLORS['text'],
                relief='flat', borderwidth=0,
                cursor='hand2',
                command=lambda k=key: self._set_mode(k),
            )
            btn.pack(side='left', fill='x', expand=True, padx=2, pady=2)
            self.tab_btns[key] = btn
        self._highlight_tab()

        # Canvas ring
        self.canvas_size = 250
        self.canvas = tk.Canvas(
            main, width=self.canvas_size, height=self.canvas_size,
            bg=COLORS['card'], highlightthickness=0,
        )
        self.canvas.pack(pady=(0, 20))

        self._draw_ring()

        # Time label (on top of canvas)
        self.time_label = tk.Label(
            main, text='25:00',
            font=('Consolas', 56, 'bold'),
            fg=COLORS['text'], bg=COLORS['card'],
        )
        self.time_label.place(in_=self.canvas, relx=0.5, rely=0.38, anchor='center')

        self.status_label = tk.Label(
            main, text='准备开始',
            font=('Segoe UI', 10),
            fg=COLORS['muted'], bg=COLORS['card'],
        )
        self.status_label.place(in_=self.canvas, relx=0.5, rely=0.62, anchor='center')

        # Controls
        ctrl = tk.Frame(main, bg=COLORS['bg'])
        ctrl.pack(pady=(0, 16))

        self._make_icon_btn(ctrl, '↻', self._reset, 38).pack(side='left', padx=8)

        self.play_btn = tk.Button(
            ctrl, text='▶', font=('', 20),
            fg='white', bg=COLORS['work'],
            activebackground=COLORS['work'],
            activeforeground='white',
            relief='flat', borderwidth=0,
            cursor='hand2',
            width=3, height=1,
            command=self._toggle,
        )
        self.play_btn.pack(side='left', padx=8)

        self._make_icon_btn(ctrl, '⏭', self._skip, 38).pack(side='left', padx=8)

        # Session dots
        dot_frame = tk.Frame(main, bg=COLORS['bg'])
        dot_frame.pack(pady=(0, 16))
        self.dot_canvases = []
        for i in range(4):
            c = tk.Canvas(dot_frame, width=14, height=14,
                          bg=COLORS['bg'], highlightthickness=0)
            c.pack(side='left', padx=5)
            self.dot_canvases.append(c)
        self._draw_dots()

        # Bottom bar: always-on-top toggle
        bottom = tk.Frame(main, bg=COLORS['bg'])
        bottom.pack(fill='x')

        cb = tk.Checkbutton(
            bottom, text='窗口置顶',
            variable=self.always_on_top,
            command=self._toggle_topmost,
            fg=COLORS['muted'], bg=COLORS['bg'],
            selectcolor=COLORS['bg'],
            activebackground=COLORS['bg'],
            activeforeground=COLORS['text'],
            font=('Segoe UI', 9),
            cursor='hand2',
        )
        cb.pack(side='left')

        # Version label / hint
        tk.Label(
            bottom, text='空格 开始/暂停 · 1/2/3 切换模式 · R 重置',
            font=('Segoe UI', 8), fg=COLORS['muted'], bg=COLORS['bg'],
        ).pack(side='right')

    def _make_icon_btn(self, parent, text, cmd, size):
        return tk.Button(
            parent, text=text, font=('', 16),
            fg=COLORS['muted'], bg=COLORS['btn_bg'],
            activebackground=COLORS['btn_hover'],
            activeforeground=COLORS['text'],
            relief='flat', borderwidth=0,
            cursor='hand2',
            width=2, height=1,
            command=cmd,
        )

    # ── Ring Drawing ───────────────────────────────

    def _draw_ring(self, progress=0):
        self.canvas.delete('all')
        cx = cy = self.canvas_size // 2
        r = 110
        sw = 10

        # Background ring
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=COLORS['ring_bg'], width=sw,
        )

        # Color
        if self.mode == 'work':
            color = COLORS['work']
        elif self.mode == 'short_break':
            color = COLORS['short_break']
        else:
            color = COLORS['long_break']

        # Progress arc
        if progress > 0:
            angle = 360 * progress
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=-angle,
                outline=color, width=sw,
                style='arc',
            )

    # ── Timer Logic ────────────────────────────────

    def _tick(self):
        if not self.running:
            return
        if self.time_left <= 0:
            self._finish_session()
            return
        self.time_left -= 1
        self._update_display()
        self.after_id = self.root.after(1000, self._tick)

    def _update_display(self):
        m, s = divmod(self.time_left, 60)
        self.time_label.config(text=f'{m:02d}:{s:02d}')

        progress = 1 - (self.time_left / self.total_time)
        self._draw_ring(progress)

        if not self.running:
            self.status_label.config(text='准备开始')
        elif self.mode == 'work':
            self.status_label.config(text='专注中...')
        elif self.mode == 'short_break':
            self.status_label.config(text='休息一下')
        else:
            self.status_label.config(text='好好放松')

        self._update_tray_title()

    def _toggle(self):
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        self.running = True
        self.play_btn.config(text='⏸', bg='#ffd43b', fg=COLORS['bg'])
        self.status_label.config(text='专注中...' if self.mode == 'work' else '计时中...')
        self.after_id = self.root.after(1000, self._tick)
        self._update_tray_menu()

    def _pause(self):
        self.running = False
        self.play_btn.config(text='▶', bg=COLORS['work'], fg='white')
        self.status_label.config(text='已暂停')
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._draw_ring(1 - self.time_left / self.total_time)
        self._update_tray_menu()

    def _reset(self):
        self._pause()
        if self.mode == 'work':
            self.time_left = WORK_TIME
        elif self.mode == 'short_break':
            self.time_left = SHORT_BREAK
        else:
            self.time_left = LONG_BREAK
        self.total_time = self.time_left
        self._update_display()

    def _skip(self):
        self._pause()
        self._finish_session()

    def _finish_session(self):
        self._pause()
        self._notify()

        if self.mode == 'work':
            self.completed += 1
            self._draw_dots()
            if self.completed % 4 == 0:
                self._set_mode('long_break')
            else:
                self._set_mode('short_break')
        else:
            self._set_mode('work')

        self._start()

    # ── Mode Switching ─────────────────────────────

    def _set_mode(self, mode):
        self._pause()
        self.mode = mode
        if mode == 'work':
            self.total_time = WORK_TIME
        elif mode == 'short_break':
            self.total_time = SHORT_BREAK
        else:
            self.total_time = LONG_BREAK
        self.time_left = self.total_time
        self._highlight_tab()
        self._update_display()

    def _highlight_tab(self):
        for key, btn in self.tab_btns.items():
            if key == self.mode:
                color = {'work': COLORS['work'],
                         'short_break': COLORS['short_break'],
                         'long_break': COLORS['long_break']}[key]
                btn.config(bg=color, fg='white', activebackground=color)
            else:
                btn.config(bg=COLORS['ring_bg'], fg=COLORS['muted'],
                           activebackground=COLORS['btn_hover'])

    # ── Session Dots ───────────────────────────────

    def _draw_dots(self):
        filled = self.completed % 4
        for i, c in enumerate(self.dot_canvases):
            c.delete('all')
            x, y = 7, 7
            r = 5
            color = COLORS['work'] if i < filled else COLORS['ring_bg']
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=color, outline='', width=0)

    # ── Always On Top ──────────────────────────────

    def _toggle_topmost(self):
        self.root.attributes('-topmost', self.always_on_top.get())

    # ── Notification ───────────────────────────────

    def _notify(self):
        if self.tray_icon:
            if self.mode == 'work':
                msg = '专注完成！休息一下吧 🍅'
            elif self.mode == 'short_break':
                msg = '休息结束，开始新的专注吧 💪'
            else:
                msg = '长休结束，开始新的专注吧 💪'
            self.tray_icon.notify(msg, title='番茄钟')

    # ── System Tray ────────────────────────────────

    def _create_tray_image(self, color='#868e96'):
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Tomato shape: red circle with green top
        draw.ellipse([12, 20, 52, 60], fill=color)
        # Small green leaf
        draw.ellipse([28, 8, 38, 22], fill='#51cf66')
        return img

    def _start_tray(self):
        img = self._create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem('显示窗口', self._show_window, default=True),
            pystray.MenuItem('开始', self._toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._quit_app),
        )
        self.tray_icon = pystray.Icon('pomodoro', img, '番茄钟', menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _update_tray_title(self):
        if self.tray_icon:
            m, s = divmod(self.time_left, 60)
            self.tray_icon.title = f'番茄钟 {m:02d}:{s:02d}'

    def _update_tray_menu(self):
        if not self.tray_icon:
            return
        action = '暂停' if self.running else '开始'
        menu = pystray.Menu(
            pystray.MenuItem('显示窗口', self._show_window, default=True),
            pystray.MenuItem(action, self._toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._quit_app),
        )
        self.tray_icon.menu = menu

    def _show_window(self):
        self.root.after(0, self._do_show_window)

    def _do_show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        self.root.withdraw()  # minimize to tray instead of closing

    def _quit_app(self):
        self.running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)


if __name__ == '__main__':
    PomodoroApp()
