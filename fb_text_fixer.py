"""
FB Text Fixer – Đăng nhập Facebook & Tự động sửa bài đăng
Dùng Selenium để điều khiển Chrome thật (tránh bị block).
"""
import re
import random
import time
import threading
import datetime as dt
import json
import os
import sys
import argparse
import unicodedata
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# ─── Quy tắc thay thế (sẽ đọc từ UI) ─────────────────────────────────────────
def apply_rules(text: str, rules: list) -> tuple[str, int]:
    """Áp dụng danh sách quy tắc [(pattern, replacement), ...] lên text."""
    count = 0
    for pattern, replacement in rules:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count

# ─── Màu sắc ─────────────────────────────────────────────────────────────────
BG_DARK  = "#1a1a2e"
BG_PANEL = "#16213e"
BG_CARD  = "#0f3460"
ACCENT   = "#e94560"
FG_LIGHT = "#eaeaea"
FG_MUTED = "#a0a0b0"
GREEN    = "#6ab04c"
YELLOW   = "#f9ca24"
FONT     = ("Segoe UI", 10)
FONT_B   = ("Segoe UI", 10, "bold")
FONT_H   = ("Segoe UI", 13, "bold")
FONT_M   = ("Consolas", 10)

# ─── App ─────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self, profile_name="default"):
        super().__init__()
        self.profile_name = profile_name
        title_suffix = f" [{profile_name}]" if profile_name != "default" else ""
        self.title(f"🛠 FB Text Fixer – Tự động sửa bài Facebook- Đa Ngôn Ngữ Bảo Ngọc 0916385682-0986183806{title_suffix}")
        self.geometry("1400x920")
        self.minsize(1200, 780)
        self.configure(bg=BG_DARK)

        self.driver = None
        self.logged_in = False
        self.posts = []   # [{el, text}, ...]
        self._stop_flag = False
        self._auto_login_started = False

        # Profile-specific paths
        base_dir = os.path.dirname(__file__)
        config_dir = self._get_appdata_dir()
        profile_suffix = f"_{profile_name}" if profile_name != "default" else ""

        # Auto-comment tab vars (bình luận vào bài trong nhóm)
        self.config_file = os.path.join(config_dir, f"fb_comment_config{profile_suffix}.json")
        self.comment_groups_cache_file = os.path.join(config_dir, f"fb_comment_groups_cache{profile_suffix}.json")
        self.selected_groups = {}  # {group_url: {var, name}}
        self.comment_groups_all = []
        self.comment_selected_urls = set()
        self.comment_group_search_var = tk.StringVar(value="")
        self.comment_text_var = tk.StringVar(value="")
        self.comment_image_path = tk.StringVar(value="")
        self.comment_selected_count_var = tk.StringVar(value="Đã chọn: 0 nhóm")
        self.comment_use_templates_var = tk.BooleanVar(value=True)
        self.comment_use_variation_var = tk.BooleanVar(value=True)
        self.comment_images_box = None
        self.comment_textboxes = []
        self.comment_mode_var = tk.StringVar(value="sequential")
        self.comment_old_posts_var = tk.BooleanVar(value=True)
        self.comment_post_count = tk.IntVar(value=3)  # Number of old posts to comment on
        self.comment_delay_min_var = tk.IntVar(value=20)
        self.comment_delay_max_var = tk.IntVar(value=60)
        self.comment_group_rest_min_var = tk.IntVar(value=2)
        self.comment_group_rest_max_var = tk.IntVar(value=5)
        self.comment_session_group_min_var = tk.IntVar(value=10)
        self.comment_session_group_max_var = tk.IntVar(value=20)
        self.comment_session_rest_min_var = tk.IntVar(value=30)
        self.comment_session_rest_max_var = tk.IntVar(value=60)
        self.monitor_enabled_var = tk.BooleanVar(value=False)
        self.monitor_interval_var = tk.IntVar(value=5)
        self.is_commenting = False
        self.monitor_thread = None
        self.monitor_stop_event = threading.Event()
        self.commented_posts_hash = set()  # Track commented posts by text hash to avoid duplicates
        self.commented_posts_uid = set()   # Track commented posts by permalink/story id (more reliable)
        self._pending_selected_group_urls = set()
        self.comment_group_text_only = set()

        # Group auto-post tab vars (đăng bài trong nhóm)
        self.group_post_config_file = os.path.join(config_dir, f"fb_group_post_config{profile_suffix}.json")
        self.group_post_groups_cache_file = os.path.join(config_dir, f"fb_group_post_groups_cache{profile_suffix}.json")
        self.group_post_selected_groups = {}  # {group_url: {var, name}}
        self.group_post_groups_all = []
        self.group_post_selected_urls = set()
        self.group_post_search_var = tk.StringVar(value="")
        self.group_post_selected_count_var = tk.StringVar(value="Đã chọn: 0 nhóm")
        self.group_post_mode_var = tk.StringVar(value="interval")  # interval | schedule
        self.group_post_template_mode_var = tk.StringVar(value="sequential")  # sequential | random
        self.group_post_skip_pending_var = tk.BooleanVar(value=False)
        self.group_post_interval_min_var = tk.IntVar(value=60)
        self.group_post_interval_max_var = tk.IntVar(value=120)
        self.group_post_group_rest_min_var = tk.IntVar(value=2)
        self.group_post_group_rest_max_var = tk.IntVar(value=5)
        self.group_post_session_group_min_var = tk.IntVar(value=10)
        self.group_post_session_group_max_var = tk.IntVar(value=20)
        self.group_post_session_rest_min_var = tk.IntVar(value=30)
        self.group_post_session_rest_max_var = tk.IntVar(value=60)
        self.group_post_daily_limit_var = tk.IntVar(value=1)
        self.group_post_thread = None
        self.group_post_stop_event = threading.Event()
        self.group_post_schedule_thread = None
        self.group_post_schedule_stop_event = threading.Event()
        self.group_post_last_run_keys = set()
        self.group_post_daily_counts = {}
        self.group_post_pending_required = {}

        # 3 post slots for group posting (used by interval and schedule)
        self.group_post_slots = []
        for _i in range(3):
            self.group_post_slots.append({
                "enabled": tk.BooleanVar(value=False),
                "mode": tk.StringVar(value="daily"),
                "times": tk.StringVar(value="08:00"),
                "weekday": tk.StringVar(value="Mon"),
                "image": tk.StringVar(value=""),
                "text_widget": None,
            })

        # Group approval tab vars (duyệt bài trong nhóm)
        self.approval_config_file = os.path.join(config_dir, f"fb_approval_config{profile_suffix}.json")
        self.approval_groups_cache_file = os.path.join(config_dir, f"fb_approval_groups_cache{profile_suffix}.json")
        self.approval_selected_groups = {}  # {group_url: {var, name}}
        self._pending_selected_approval_urls = set()
        self.managed_group_urls = set()
        self.approval_interval_var = tk.IntVar(value=5)  # phút giữa các lần quét
        self.approval_mode_var = tk.StringVar(value="interval")  # "once" hoặc "interval"
        self.approval_auto_approve_safe = tk.BooleanVar(value=True)
        self.approval_thread = None
        self.approval_stop_event = threading.Event()
        self.approval_keywords_box = None  # sẽ gán trong UI
        self.approval_group_list_frame = None

        # Scheduler (auto-post on personal profile)
        self.schedule_config_file = os.path.join(config_dir, f"fb_schedule_config{profile_suffix}.json")
        self.scheduler_thread = None
        self.scheduler_stop_event = threading.Event()
        self.scheduler_last_run_keys = set()  # prevent double-posting the same scheduled slot

        # 3 post slots UI vars (widgets created later)
        self.schedule_slots = []
        for _i in range(3):
            self.schedule_slots.append({
                "enabled": tk.BooleanVar(value=False),
                "mode": tk.StringVar(value="daily"),
                # Flexible times: comma-separated HH:MM list for daily; weekly uses weekday + time
                "times": tk.StringVar(value="08:00"),
                "weekday": tk.StringVar(value="Mon"),
                "image": tk.StringVar(value=""),
                "text_widget": None,
            })

        self._build_ui()
        self._load_comment_config()
        self._load_approval_config()
        self._restore_groups_cache_on_start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Sau khi UI sẵn sàng, tự động mở Chrome & kiểm tra đăng nhập Facebook một lần.
        # Người dùng vẫn có thể nhấn nút "Mở Chrome & Đăng nhập" như cũ nếu cần.
        try:
            self.after(1200, self._auto_login_on_start)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # Header (compact)
        hdr = tk.Frame(self, bg=BG_CARD, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📝  FB Text Fixer", font=("Segoe UI", 14, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left", padx=20)
        tk.Label(hdr, text="Đăng nhập Facebook → Tải bài đăng → Tự động sửa",
                 font=FONT, bg=BG_CARD, fg=FG_MUTED).pack(side="left")

        # Notebook (tabs)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG_MUTED,
                        padding=[14, 6], font=FONT_B)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", FG_LIGHT)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        tab1 = tk.Frame(nb, bg=BG_DARK); nb.add(tab1, text="🔑  Đăng nhập & Tự động sửa")
        tab2 = tk.Frame(nb, bg=BG_DARK); nb.add(tab2, text="💬  Auto Comment Nhóm")
        tab3 = tk.Frame(nb, bg=BG_DARK); nb.add(tab3, text="🗓️  Đăng bài theo lịch")
        tab4 = tk.Frame(nb, bg=BG_DARK); nb.add(tab4, text="✅  Duyệt bài nhóm")
        tab5 = tk.Frame(nb, bg=BG_DARK); nb.add(tab5, text="🧾  Auto đăng bài nhóm")

        self._build_tab_auto(tab1)
        self._build_tab_comment(tab2)
        self._build_tab_scheduler(tab3)
        self._build_tab_group_approval(tab4)
        self._build_tab_group_post(tab5)

        # Status bar
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        tk.Label(self, textvariable=self.status_var, font=("Segoe UI", 9),
                 bg=BG_CARD, fg=FG_MUTED, anchor="w", pady=5, padx=12
                 ).pack(fill="x", side="bottom")

    # ── Tab 3: Scheduler ────────────────────────────────────────────────────
    def _build_tab_scheduler(self, parent):
        wrap = tk.Frame(parent, bg=BG_DARK)
        wrap.pack(fill="both", expand=True, padx=14, pady=(10, 10))

        hdr = tk.Frame(wrap, bg=BG_DARK)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="Tự động đăng bài theo lịch trên trang cá nhân (3 mẫu nội dung)",
            font=FONT_B,
            bg=BG_DARK,
            fg=FG_LIGHT,
        ).pack(side="left")

        btns = tk.Frame(hdr, bg=BG_DARK)
        btns.pack(side="right")
        self.btn_save_schedule = self._btn(btns, "💾  Lưu lịch", self._save_schedule_config, "#2d2d44")
        self.btn_save_schedule.pack(side="left", padx=(0, 6))
        self.btn_start_schedule = self._btn(btns, "▶️  Bắt đầu", self._start_scheduler, "#1f6feb")
        self.btn_start_schedule.pack(side="left", padx=(0, 6))
        self.btn_stop_schedule = self._btn(btns, "⏹  Dừng", self._stop_scheduler, "#e74c3c")
        self.btn_stop_schedule.pack(side="left")
        self._set_run_buttons(self.btn_start_schedule, self.btn_stop_schedule, False, "#1f6feb", "#e74c3c")

        tk.Label(
            wrap,
            text="Lưu ý: nếu Facebook đang hạn chế thao tác (spam/rate limit), tab này sẽ tự dừng.",
            font=FONT,
            bg=BG_DARK,
            fg=FG_MUTED,
        ).pack(anchor="w", pady=(8, 6))

        # Scrollable slots (vertical) so small windows can still access slot 3
        canvas = tk.Canvas(wrap, bg=BG_DARK, highlightthickness=0)
        vsb = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        slots_frame = tk.Frame(canvas, bg=BG_DARK)
        canvas.create_window((0, 0), window=slots_frame, anchor="nw")

        def _on_frame_config(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        slots_frame.bind("<Configure>", _on_frame_config)

        def _on_mousewheel(e):
            try:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        weekday_options = [
            ("Mon", "Thứ 2"), ("Tue", "Thứ 3"), ("Wed", "Thứ 4"),
            ("Thu", "Thứ 5"), ("Fri", "Thứ 6"), ("Sat", "Thứ 7"), ("Sun", "Chủ nhật")
        ]

        def _adjust_time(var, delta):
            """Adjust the first HH:MM in the times string by delta minutes."""
            raw = var.get().strip()
            if not raw:
                var.set("08:00")
                return
            parts = [p.strip() for p in raw.split(",")]
            if parts:
                first = parts[0]
                try:
                    hh, mm = first.split(":")
                    total = int(hh) * 60 + int(mm) + delta
                    total = max(0, min(23 * 60 + 59, total))
                    parts[0] = f"{total // 60:02d}:{total % 60:02d}"
                    var.set(", ".join(parts))
                except Exception:
                    pass

        def _make_adjust_cmd(var, delta, entry_widget):
            def _cmd():
                try:
                    if entry_widget:
                        entry_widget.focus_set()
                except Exception:
                    pass
                _adjust_time(var, delta)
                try:
                    if entry_widget:
                        entry_widget.update_idletasks()
                except Exception:
                    pass
            return _cmd

        def _weekday_label(code):
            for c, lab in weekday_options:
                if c == code:
                    return lab
            return code

        for i in range(3):
            slot = self.schedule_slots[i]
            lf = tk.LabelFrame(
                slots_frame,
                text=f"  Nội dung {i+1}  ",
                font=FONT_B,
                bg=BG_DARK,
                fg=FG_MUTED,
                bd=1,
                relief="groove",
            )
            lf.pack(fill="both", expand=True, pady=(0, 10))

            top = tk.Frame(lf, bg=BG_DARK)
            top.pack(fill="x", padx=10, pady=(8, 6))

            tk.Checkbutton(
                top,
                text="Bật lịch cho nội dung này",
                variable=slot["enabled"],
                font=FONT,
                bg=BG_DARK,
                fg=FG_LIGHT,
                activebackground=BG_DARK,
                activeforeground=FG_LIGHT,
                selectcolor=BG_DARK,
            ).pack(side="left")

            tk.Label(top, text="Loại lịch:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(12, 4))
            mode = ttk.Combobox(
                top,
                values=["daily", "weekly"],
                textvariable=slot["mode"],
                width=8,
                state="readonly",
            )
            mode.pack(side="left")
            tk.Label(top, text="Giờ đăng:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(12, 4))
            tk.Entry(top, textvariable=slot["times"], width=26, font=FONT,
                     bg=BG_PANEL, fg=FG_LIGHT, relief="flat").pack(side="left")

            # Arrow buttons to adjust time - separate for hours and minutes
            def _adjust_time(var, delta):
                """Adjust the first HH:MM in the times string by delta minutes."""
                raw = var.get().strip()
                if not raw:
                    var.set("08:00")
                    return
                parts = [p.strip() for p in raw.split(",")]
                if parts:
                    first = parts[0]
                    try:
                        hh, mm = first.split(":")
                        total = int(hh) * 60 + int(mm) + delta
                        total = max(0, min(23 * 60 + 59, total))
                        parts[0] = f"{total // 60:02d}:{total % 60:02d}"
                        var.set(", ".join(parts))
                    except Exception:
                        pass

            # Hour adjustment buttons
            hour_frame = tk.Frame(top, bg=BG_DARK)
            hour_frame.pack(side="left", padx=(4, 0))
            tk.Label(hour_frame, text="Giờ", font=("Segoe UI", 7), bg=BG_DARK, fg=FG_MUTED).pack(side="top")
            tk.Button(
                hour_frame, text="▲", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=lambda v=slot["times"]: _adjust_time(v, 60),
            ).pack(side="top", pady=0)
            tk.Button(
                hour_frame, text="▼", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=lambda v=slot["times"]: _adjust_time(v, -60),
            ).pack(side="top", pady=0)

            # Minute adjustment buttons
            min_frame = tk.Frame(top, bg=BG_DARK)
            min_frame.pack(side="left", padx=(2, 0))
            tk.Label(min_frame, text="Phút", font=("Segoe UI", 7), bg=BG_DARK, fg=FG_MUTED).pack(side="top")
            tk.Button(
                min_frame, text="▲", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=lambda v=slot["times"]: _adjust_time(v, 1),
            ).pack(side="top", pady=0)
            tk.Button(
                min_frame, text="▼", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=lambda v=slot["times"]: _adjust_time(v, -1),
            ).pack(side="top", pady=0)

            tk.Label(top, text="(VD: 08:00 hoặc 08:00, 12:30, 19:00)",
                     font=("Segoe UI", 9), bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(8, 0))

            sched = tk.Frame(lf, bg=BG_DARK)
            sched.pack(fill="x", padx=10)

            tk.Label(sched, text="Thứ (chỉ áp dụng weekly):", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
            wd_menu = ttk.Combobox(
                sched,
                values=[c for c, _lab in weekday_options],
                textvariable=slot["weekday"],
                width=5,
                state="readonly",
            )
            wd_menu.pack(side="left", padx=(6, 6))
            tk.Label(sched, text="(Mon..Sun)", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

            img_row = tk.Frame(lf, bg=BG_DARK)
            img_row.pack(fill="x", padx=10, pady=(8, 6))
            tk.Label(img_row, text="Ảnh (tuỳ chọn):", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
            tk.Entry(img_row, textvariable=slot["image"], font=FONT, width=80,
                     bg=BG_PANEL, fg=FG_LIGHT, relief="flat").pack(side="left", padx=(6, 6), fill="x", expand=True)
            tk.Button(
                img_row,
                text="Chọn ảnh",
                command=lambda idx=i: self._choose_schedule_image(idx),
                font=FONT_B,
                bg=BG_PANEL,
                fg=FG_LIGHT,
                activebackground=BG_CARD,
                activeforeground=FG_LIGHT,
                relief="flat",
                cursor="hand2",
                padx=10,
                pady=4,
            ).pack(side="left")

            txt = tk.Text(lf, height=4, font=FONT, bg=BG_PANEL, fg=FG_LIGHT, insertbackground=FG_LIGHT,
                          relief="flat", wrap="word")
            txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            slot["text_widget"] = txt

        # Load persisted schedule config
        self._load_schedule_config()

    # ── Tab 5: Auto đăng bài nhóm ───────────────────────────────────────────
    def _build_tab_group_post(self, parent):
        top_control = tk.Frame(parent, bg=BG_DARK)
        top_control.pack(fill="x", padx=14, pady=(10, 6))

        left_btns = tk.Frame(top_control, bg=BG_DARK)
        left_btns.pack(side="left")
        self._btn(left_btns, "🔄  Tải nhóm", self._fetch_groups, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(left_btns, "🔎  Quét kiểm duyệt", self._scan_group_post_pending_for_groups, "#6ab04c").pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☑️  Chọn tất cả", lambda: self._toggle_all_group_post(True), "#6ab04c").pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☐  Bỏ chọn", lambda: self._toggle_all_group_post(False), "#2d2d44").pack(side="left")

        right_btns = tk.Frame(top_control, bg=BG_DARK)
        right_btns.pack(side="right")
        self.btn_start_group_post = self._btn(right_btns, "▶️  Bắt đầu", self._start_group_posting, ACCENT)
        self.btn_start_group_post.pack(side="left", padx=(0, 6))
        self.btn_stop_group_post = self._btn(right_btns, "⏹  Dừng", self._stop_group_posting, "#e74c3c")
        self.btn_stop_group_post.pack(side="left", padx=(0, 6))
        self._btn(right_btns, "💾  Lưu", self._save_group_post_config, "#6ab04c").pack(side="left")
        self._set_run_buttons(self.btn_start_group_post, self.btn_stop_group_post, False, ACCENT, "#e74c3c")

        gf = tk.LabelFrame(parent, text="  Chọn nhóm Facebook (dùng lại danh sách Auto Comment)  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        gf.pack(fill="x", padx=14, pady=(4, 6))

        search_row = tk.Frame(gf, bg=BG_DARK)
        search_row.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(search_row, text="Tìm nhanh:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        search_entry = tk.Entry(
            search_row,
            textvariable=self.group_post_search_var,
            font=FONT,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            relief="flat",
        )
        search_entry.pack(side="left", padx=(8, 6), fill="x", expand=True)
        tk.Button(
            search_row,
            text="Xoá",
            font=FONT_B,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            activebackground=BG_CARD,
            activeforeground=FG_LIGHT,
            relief="flat",
            cursor="hand2",
            command=lambda: self.group_post_search_var.set(""),
        ).pack(side="left")

        group_canvas_frame = tk.Frame(gf, bg=BG_DARK)
        group_canvas_frame.pack(fill="x", padx=10, pady=(4, 8))
        group_canvas = tk.Canvas(group_canvas_frame, bg=BG_PANEL, highlightthickness=0, height=200)
        group_scrollbar = tk.Scrollbar(group_canvas_frame, orient="vertical", command=group_canvas.yview)
        self.group_post_list_frame = tk.Frame(group_canvas, bg=BG_PANEL)

        group_canvas.create_window((0, 0), window=self.group_post_list_frame, anchor="nw")
        group_canvas.configure(yscrollcommand=group_scrollbar.set)
        group_canvas.pack(side="left", fill="both", expand=True)
        group_scrollbar.pack(side="right", fill="y")

        def _on_group_post_frame_configure(_event=None):
            group_canvas.configure(scrollregion=group_canvas.bbox("all"))
        self.group_post_list_frame.bind("<Configure>", _on_group_post_frame_configure)

        try:
            self.group_post_search_var.trace_add("write", lambda *_: self._apply_group_post_filter())
        except Exception:
            pass

        tk.Label(
            gf,
            textvariable=self.group_post_selected_count_var,
            font=FONT,
            bg=BG_DARK,
            fg=FG_MUTED,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 4))

        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=14, pady=(4, 6))

        left_col = tk.Frame(body, bg=BG_DARK)
        right_col = tk.Frame(body, bg=BG_DARK)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right_col.pack(side="left", fill="both", expand=True)

        # Left: content slots (scrollable)
        slot_canvas = tk.Canvas(left_col, bg=BG_DARK, highlightthickness=0)
        slot_scroll = tk.Scrollbar(left_col, orient="vertical", command=slot_canvas.yview)
        slot_canvas.configure(yscrollcommand=slot_scroll.set)
        slot_scroll.pack(side="right", fill="y")
        slot_canvas.pack(side="left", fill="both", expand=True)

        cf = tk.LabelFrame(slot_canvas, text="  Nội dung đăng (3 mẫu)  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        slot_canvas.create_window((0, 0), window=cf, anchor="nw")

        def _on_cf_configure(_e=None):
            try:
                slot_canvas.configure(scrollregion=slot_canvas.bbox("all"))
            except Exception:
                pass
        cf.bind("<Configure>", _on_cf_configure)

        def _adjust_time(var, delta):
            """Adjust the first HH:MM in the times string by delta minutes."""
            raw = var.get().strip()
            if not raw:
                var.set("08:00")
                return
            parts = [p.strip() for p in raw.split(",")]
            if parts:
                first = parts[0]
                try:
                    hh, mm = first.split(":")
                    total = int(hh) * 60 + int(mm) + delta
                    total = max(0, min(23 * 60 + 59, total))
                    parts[0] = f"{total // 60:02d}:{total % 60:02d}"
                    var.set(", ".join(parts))
                except Exception:
                    pass

        def _make_adjust_cmd(var, delta, entry_widget):
            def _cmd():
                try:
                    if entry_widget:
                        entry_widget.focus_set()
                except Exception:
                    pass
                _adjust_time(var, delta)
                try:
                    if entry_widget:
                        entry_widget.update_idletasks()
                except Exception:
                    pass
            return _cmd

        weekday_options = [
            ("Mon", "Thứ 2"), ("Tue", "Thứ 3"), ("Wed", "Thứ 4"),
            ("Thu", "Thứ 5"), ("Fri", "Thứ 6"), ("Sat", "Thứ 7"), ("Sun", "Chủ nhật")
        ]

        for i in range(3):
            slot = self.group_post_slots[i]
            lf = tk.LabelFrame(cf, text=f"  Mẫu {i+1}  ", font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
            lf.pack(fill="x", padx=10, pady=(6, 6))

            top = tk.Frame(lf, bg=BG_DARK)
            top.pack(fill="x", padx=8, pady=(6, 4))
            tk.Checkbutton(
                top,
                text="Bật mẫu này",
                variable=slot["enabled"],
                font=FONT,
                bg=BG_DARK,
                fg=FG_LIGHT,
                activebackground=BG_DARK,
                activeforeground=FG_LIGHT,
                selectcolor=BG_DARK,
            ).pack(side="left")

            tk.Label(top, text="Loại lịch:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(10, 4))
            ttk.Combobox(top, values=["daily", "weekly"], textvariable=slot["mode"], width=8, state="readonly").pack(side="left")
            tk.Label(top, text="Giờ đăng:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(10, 4))
            time_entry = tk.Entry(top, textvariable=slot["times"], width=22, font=FONT, bg=BG_PANEL, fg=FG_LIGHT, relief="flat")
            time_entry.pack(side="left")

            hour_frame = tk.Frame(top, bg=BG_DARK)
            hour_frame.pack(side="left", padx=(4, 0))
            tk.Label(hour_frame, text="Giờ", font=("Segoe UI", 7), bg=BG_DARK, fg=FG_MUTED).pack(side="top")
            tk.Button(
                hour_frame, text="▲", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=_make_adjust_cmd(slot["times"], 60, time_entry),
            ).pack(side="top", pady=0)
            tk.Button(
                hour_frame, text="▼", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=_make_adjust_cmd(slot["times"], -60, time_entry),
            ).pack(side="top", pady=0)

            min_frame = tk.Frame(top, bg=BG_DARK)
            min_frame.pack(side="left", padx=(2, 0))
            tk.Label(min_frame, text="Phút", font=("Segoe UI", 7), bg=BG_DARK, fg=FG_MUTED).pack(side="top")
            tk.Button(
                min_frame, text="▲", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=_make_adjust_cmd(slot["times"], 1, time_entry),
            ).pack(side="top", pady=0)
            tk.Button(
                min_frame, text="▼", font=("Segoe UI", 8), width=2,
                bg=BG_PANEL, fg=FG_LIGHT, activebackground="#2a2a4e", activeforeground=FG_LIGHT,
                relief="flat", cursor="hand2", bd=0,
                command=_make_adjust_cmd(slot["times"], -1, time_entry),
            ).pack(side="top", pady=0)

            tk.Label(top, text="Thứ:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(10, 4))
            ttk.Combobox(top, values=[c for c, _lab in weekday_options], textvariable=slot["weekday"], width=5, state="readonly").pack(side="left")

            img_row = tk.Frame(lf, bg=BG_DARK)
            img_row.pack(fill="x", padx=8, pady=(2, 4))
            tk.Label(img_row, text="Ảnh (tuỳ chọn):", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
            tk.Entry(img_row, textvariable=slot["image"], font=FONT, width=50, bg=BG_PANEL, fg=FG_LIGHT, relief="flat").pack(side="left", padx=(6, 6), fill="x", expand=True)
            tk.Button(
                img_row,
                text="Chọn ảnh",
                command=lambda idx=i: self._choose_group_post_image(idx),
                font=FONT_B,
                bg=BG_PANEL,
                fg=FG_LIGHT,
                activebackground=BG_CARD,
                activeforeground=FG_LIGHT,
                relief="flat",
                cursor="hand2",
                padx=10,
                pady=2,
            ).pack(side="left")

            txt = tk.Text(lf, height=4, font=FONT, bg=BG_PANEL, fg=FG_LIGHT, insertbackground=FG_LIGHT,
                          relief="flat", wrap="word")
            txt.pack(fill="x", padx=8, pady=(0, 6))
            slot["text_widget"] = txt

        # Right: settings
        sf = tk.LabelFrame(right_col, text="  Cài đặt chạy  ", font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        sf.pack(fill="both", expand=True)

        mode_row = tk.Frame(sf, bg=BG_DARK)
        mode_row.pack(fill="x", padx=14, pady=(6, 4))
        tk.Label(mode_row, text="Chế độ:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Radiobutton(mode_row, text="Chu kỳ", variable=self.group_post_mode_var, value="interval",
                       font=FONT, bg=BG_DARK, fg=FG_LIGHT, selectcolor=BG_DARK).pack(side="left", padx=(8, 8))
        tk.Radiobutton(mode_row, text="Theo lịch", variable=self.group_post_mode_var, value="schedule",
                       font=FONT, bg=BG_DARK, fg=FG_LIGHT, selectcolor=BG_DARK).pack(side="left")

        template_row = tk.Frame(sf, bg=BG_DARK)
        template_row.pack(fill="x", padx=14, pady=(4, 4))
        tk.Label(template_row, text="Chọn mẫu:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        ttk.Combobox(template_row, values=["sequential", "random"], textvariable=self.group_post_template_mode_var,
                     width=12, state="readonly").pack(side="left", padx=(8, 6))
        tk.Label(template_row, text="(chu kỳ dùng mẫu bật)", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        skip_row = tk.Frame(sf, bg=BG_DARK)
        skip_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Checkbutton(
            skip_row,
            text="Bỏ qua nhóm cần kiểm duyệt",
            variable=self.group_post_skip_pending_var,
            font=FONT,
            bg=BG_DARK,
            fg=FG_LIGHT,
            activebackground=BG_DARK,
            activeforeground=ACCENT,
            selectcolor=BG_DARK,
        ).pack(anchor="w")

        interval_row = tk.Frame(sf, bg=BG_DARK)
        interval_row.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(interval_row, text="Chu kỳ quét:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(interval_row, from_=1, to=720, textvariable=self.group_post_interval_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 4))
        tk.Label(interval_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(interval_row, from_=1, to=720, textvariable=self.group_post_interval_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(4, 4))
        tk.Label(interval_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")

        rest_row = tk.Frame(sf, bg=BG_DARK)
        rest_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(rest_row, text="Nghỉ sau mỗi nhóm:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(rest_row, from_=0, to=120, textvariable=self.group_post_group_rest_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 4))
        tk.Label(rest_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(rest_row, from_=0, to=120, textvariable=self.group_post_group_rest_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(4, 4))
        tk.Label(rest_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")

        session_row = tk.Frame(sf, bg=BG_DARK)
        session_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(session_row, text="Giới hạn nhóm/phiên:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(session_row, from_=1, to=200, textvariable=self.group_post_session_group_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 4))
        tk.Label(session_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(session_row, from_=1, to=200, textvariable=self.group_post_session_group_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(4, 4))
        tk.Label(session_row, text="nhóm", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        session_rest_row = tk.Frame(sf, bg=BG_DARK)
        session_rest_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(session_rest_row, text="Nghỉ giữa phiên:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(session_rest_row, from_=1, to=240, textvariable=self.group_post_session_rest_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 4))
        tk.Label(session_rest_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(session_rest_row, from_=1, to=240, textvariable=self.group_post_session_rest_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(4, 4))
        tk.Label(session_rest_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")

        limit_row = tk.Frame(sf, bg=BG_DARK)
        limit_row.pack(fill="x", padx=14, pady=(2, 6))
        tk.Label(limit_row, text="Giới hạn bài/nhóm/ngày:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(limit_row, from_=1, to=20, textvariable=self.group_post_daily_limit_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT, buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 4))

        self._load_group_post_config()

    def _choose_schedule_image(self, idx):
        filename = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")]
        )
        if filename:
            self.schedule_slots[idx]["image"].set(filename)
            self._log(f"📷 [Lịch] Đã chọn ảnh nội dung {idx+1}: {os.path.basename(filename)}", "info")

    def _save_schedule_config(self):
        try:
            slots = []
            for s in self.schedule_slots:
                txt = ""
                try:
                    if s.get("text_widget") is not None:
                        txt = s["text_widget"].get("1.0", "end-1c").strip()
                except Exception:
                    txt = ""
                slots.append({
                    "enabled": bool(s["enabled"].get()),
                    "mode": s["mode"].get(),
                    "times": s["times"].get(),
                    "weekday": s["weekday"].get(),
                    "image": s["image"].get(),
                    "text": txt,
                })

            config = {"slots": slots}
            with open(self.schedule_config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self._log(f"💾 [Lịch] Đã lưu cấu hình: {self.schedule_config_file}", "ok")
            messagebox.showinfo("Thành công", "Đã lưu lịch đăng bài!")
        except Exception as e:
            self._log(f"❌ [Lịch] Lỗi lưu config: {e}", "err")

    def _load_schedule_config(self):
        try:
            if not os.path.exists(self.schedule_config_file):
                return
            with open(self.schedule_config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.after(100, lambda: self._apply_loaded_schedule_config(config))
        except Exception:
            return

    def _apply_loaded_schedule_config(self, config):
        try:
            slots = (config or {}).get("slots") or []
            for i in range(min(3, len(slots))):
                s = slots[i]
                ui = self.schedule_slots[i]
                ui["enabled"].set(bool(s.get("enabled", False)))
                # Backward compat: old fields (recurrence/time1/time2)
                if "mode" in s or "times" in s:
                    ui["mode"].set(s.get("mode", "daily"))
                    ui["times"].set(s.get("times", "08:00"))
                else:
                    rec = s.get("recurrence", "daily_1")
                    if rec.startswith("weekly"):
                        ui["mode"].set("weekly")
                        ui["times"].set(s.get("time1", "08:00"))
                    elif rec == "daily_2":
                        ui["mode"].set("daily")
                        t1 = s.get("time1", "08:00")
                        t2 = s.get("time2", "18:00")
                        ui["times"].set(f"{t1}, {t2}")
                    else:
                        ui["mode"].set("daily")
                        ui["times"].set(s.get("time1", "08:00"))
                ui["weekday"].set(s.get("weekday", "Mon"))
                ui["image"].set(s.get("image", ""))
                if ui.get("text_widget") is not None:
                    ui["text_widget"].delete("1.0", "end")
                    ui["text_widget"].insert("1.0", s.get("text", ""))
            self._log("📂 [Lịch] Đã load cấu hình", "info")
        except Exception:
            pass

    def _start_scheduler(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        enabled_any = any(s["enabled"].get() for s in self.schedule_slots)
        if not enabled_any:
            messagebox.showwarning("Chưa bật lịch", "Bật ít nhất 1 nội dung để chạy lịch!")
            return

        self.scheduler_last_run_keys.clear()
        self.scheduler_stop_event.clear()
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return

        self._set_run_buttons(self.btn_start_schedule, self.btn_stop_schedule, True, "#1f6feb", "#e74c3c")
        self._log("🗓️ [Lịch] Bắt đầu chạy lịch đăng bài...", "info")
        self.scheduler_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
        self.scheduler_thread.start()

    def _stop_scheduler(self):
        self.scheduler_stop_event.set()
        self._set_run_buttons(self.btn_start_schedule, self.btn_stop_schedule, False, "#1f6feb", "#e74c3c")
        self._log("⏹️ [Lịch] Đã dừng", "warn")

    def _scheduler_worker(self):
        import datetime as _dt

        def _parse_hhmm(s):
            try:
                s = (s or "").strip()
                parts = s.split(":")
                if len(parts) != 2:
                    return None
                hh = int(parts[0]); mm = int(parts[1])
                if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                    return None
                return hh, mm
            except Exception:
                return None

        def _parse_times_list(s):
            out = []
            raw = (s or "").split(",")
            for item in raw:
                t = _parse_hhmm(item)
                if t:
                    out.append(t)
            # dedupe, keep order
            seen = set(); uniq = []
            for hh, mm in out:
                key = f"{hh:02d}:{mm:02d}"
                if key in seen:
                    continue
                seen.add(key)
                uniq.append((hh, mm))
            return uniq

        weekday_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

        try:
            while not self.scheduler_stop_event.is_set():
                try:
                    if self._is_action_blocked():
                        self._log("⛔ [Lịch] Facebook đang hạn chế thao tác. Tự dừng để tránh bị chặn thêm.", "err")
                        try:
                            self._close_all_dialogs(aggressive=True)
                        except Exception:
                            pass
                        self.scheduler_stop_event.set()
                        break

                    now = _dt.datetime.now()
                    for idx, slot in enumerate(self.schedule_slots):
                        if self.scheduler_stop_event.is_set():
                            break
                        if not slot["enabled"].get():
                            continue

                        mode = slot["mode"].get()
                        times = _parse_times_list(slot["times"].get())
                        wd = weekday_map.get(slot["weekday"].get(), 0)

                        candidates = []
                        if mode == "weekly":
                            if now.weekday() == wd:
                                for (hh, mm) in times[:6]:
                                    candidates.append((now.replace(hour=hh, minute=mm, second=0, microsecond=0), f"w{hh:02d}{mm:02d}"))
                        else:
                            for (hh, mm) in times[:6]:
                                candidates.append((now.replace(hour=hh, minute=mm, second=0, microsecond=0), f"d{hh:02d}{mm:02d}"))

                        for target_dt, tag in candidates:
                            # Due window: within 2 minutes after target time
                            delta = (now - target_dt).total_seconds()
                            if delta < 0 or delta > 120:
                                continue
                            run_key = f"slot{idx+1}:{target_dt.strftime('%Y%m%d')}:{tag}:{target_dt.strftime('%H%M')}"
                            if run_key in self.scheduler_last_run_keys:
                                continue

                            # Gather content
                            text = ""
                            try:
                                tw = slot.get("text_widget")
                                if tw is not None:
                                    text = tw.get("1.0", "end-1c").strip()
                            except Exception:
                                text = ""

                            img = slot["image"].get().strip()
                            if (not text) and (not img):
                                self._log(f"⚠️ [Lịch] Nội dung {idx+1} trống, bỏ qua lần đăng.", "warn")
                                self.scheduler_last_run_keys.add(run_key)
                                continue

                            self._log(f"🕒 [Lịch] Đến giờ đăng nội dung {idx+1} ({mode})...", "info")
                            ok = self._post_to_profile(text, img, stop_event=self.scheduler_stop_event, log_tag="[Lịch]")
                            self.scheduler_last_run_keys.add(run_key)
                            if ok:
                                self._log(f"✅ [Lịch] Đã đăng nội dung {idx+1}", "ok")
                            else:
                                self._log(f"⚠️ [Lịch] Đăng nội dung {idx+1} có thể chưa thành công", "warn")

                    # poll interval
                    if self.scheduler_stop_event.wait(20):
                        break

                except Exception as e:
                    self._log(f"❌ [Lịch] Error: {e}", "err")
                    if self.scheduler_stop_event.wait(30):
                        break
        finally:
            self._log("🔕 [Lịch] Stopped", "warn")
            try:
                self.after(0, lambda: self._set_run_buttons(self.btn_start_schedule, self.btn_stop_schedule, False, "#1f6feb", "#e74c3c"))
            except Exception:
                pass

    def _post_to_profile(self, text, img_path, target_url=None, stop_event=None, log_tag="[Lịch]"):
        """Best-effort: open composer, fill text, attach image, click Next/Post."""
        try:
            if not self.driver:
                return False
            if self._is_action_blocked():
                return False

            text = (text or "").strip()
            img_path = (img_path or "").strip()
            debug_sched = True
            composer_root = [None]

            def _stop_requested():
                try:
                    if stop_event is not None:
                        return bool(stop_event.is_set())
                    return bool(self.scheduler_stop_event.is_set())
                except Exception:
                    return False

            def _top_dialog_js_prelude():
                return r"""
                function _isVisible(el){
                    try {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        if (r.width < 50 || r.height < 50) return false;
                        var st = window.getComputedStyle(el);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        if (parseFloat(st.opacity || '1') <= 0.01) return false;
                        return true;
                    } catch(e){ return false; }
                }
                function _topDialog(){
                    var ds = Array.from(document.querySelectorAll('[role="dialog"]')).filter(_isVisible);
                    if (!ds.length) return null;
                    var best = ds[0];
                    var bestZ = -999999;
                    for (var i=0;i<ds.length;i++) {
                        var z = 0;
                        try { z = parseInt(window.getComputedStyle(ds[i]).zIndex || '0', 10) || 0; } catch(e) { z = 0; }
                        if (z > bestZ || (z === bestZ && i === ds.length - 1)) { bestZ = z; best = ds[i]; }
                    }
                    return best;
                }
                function _norm(s){ return (s||'').replace(/\s+/g,' ').trim().toLowerCase(); }
                function _isEnabled(el){
                    try {
                        if (!el) return false;
                        if (el.getAttribute('disabled') !== null) return false;
                        var ad = (el.getAttribute('aria-disabled')||'').toLowerCase();
                        if (ad === 'true') return false;
                    } catch(e) {}
                    return true;
                }
                """

            def _wait_top_dialog(timeout=15):
                end = time.time() + timeout
                while time.time() < end and not _stop_requested():
                    if self._is_action_blocked():
                        return None
                    try:
                        dlg = self.driver.execute_script(_top_dialog_js_prelude() + "return _topDialog();")
                    except Exception:
                        dlg = None
                    if dlg:
                        return dlg
                    time.sleep(0.25)
                return None

            def _is_composer_dialog(dlg):
                try:
                    return bool(self.driver.execute_script(
                        _top_dialog_js_prelude()
                        + """
                        var d = arguments[0];
                        if (!d) return false;
                        var t = _norm(d.innerText || d.textContent || '');
                        if (t.indexOf('tạo bài viết') !== -1 ||
                            t.indexOf('tao bai viet') !== -1 ||
                            t.indexOf('create post') !== -1 ||
                            t.indexOf('thêm vào bài viết') !== -1 ||
                            t.indexOf('them vao bai viet') !== -1 ||
                            t.indexOf('add to your post') !== -1) return true;
                        var eds = d.querySelectorAll('[role="textbox"], [contenteditable="true"], [contenteditable="plaintext-only"]');
                        for (var i=0;i<eds.length;i++){
                            var a = _norm(eds[i].getAttribute('aria-label') || '');
                            var p = _norm(eds[i].getAttribute('aria-placeholder') || eds[i].getAttribute('data-placeholder') || '');
                            var isComment = (a.indexOf('bình luận') !== -1 || a.indexOf('trả lời') !== -1 || a.indexOf('comment') !== -1 || a.indexOf('reply') !== -1 ||
                                            p.indexOf('bình luận') !== -1 || p.indexOf('trả lời') !== -1 || p.indexOf('comment') !== -1 || p.indexOf('reply') !== -1);
                            if (!isComment) return true;
                        }
                        return false;
                        """,
                        dlg,
                    ))
                except Exception:
                    return False

            def _dismiss_notification_dialogs():
                try:
                    return bool(self.driver.execute_script(
                        _top_dialog_js_prelude()
                        + """
                        var ds = Array.from(document.querySelectorAll('[role="dialog"]')).filter(_isVisible);
                        var closed = false;
                        for (var i=0;i<ds.length;i++){
                            var d = ds[i];
                            var t = _norm(d.innerText || d.textContent || '');
                            if (t.indexOf('thông báo') === -1 && t.indexOf('notification') === -1) continue;
                            var btns = Array.from(d.querySelectorAll('button, [role="button"]'));
                            for (var j=0;j<btns.length;j++){
                                var bt = _norm(btns[j].innerText || btns[j].textContent || '');
                                var bl = _norm(btns[j].getAttribute('aria-label') || '');
                                if (bt === 'đóng' || bt === 'ok' || bt === 'đồng ý' || bt === 'close' || bt === 'okay' ||
                                    bl.indexOf('đóng') !== -1 || bl.indexOf('close') !== -1) {
                                    try { btns[j].click(); closed = true; break; } catch(e) {}
                                }
                            }
                            if (closed) break;
                        }
                        return closed;
                        """
                    ))
                except Exception:
                    return False

            def _open_composer_dialog():
                if _stop_requested() or self._is_action_blocked():
                    return None

                # Go to target URL (group) or profile (default)
                try:
                    if target_url:
                        self.driver.get(target_url)
                    else:
                        self.driver.get("https://www.facebook.com/me")
                except Exception:
                    try:
                        self.driver.get("https://www.facebook.com/")
                    except Exception:
                        return None

                # Let the feed render a bit
                for _ in range(40):
                    if _stop_requested() or self._is_action_blocked():
                        return None
                    try:
                        self.driver.execute_script("window.scrollTo(0,0);")
                    except Exception:
                        pass
                    time.sleep(0.25)
                    if _dismiss_notification_dialogs():
                        time.sleep(0.4)
                    dlg = _wait_top_dialog(timeout=0.01)
                    if dlg and _is_composer_dialog(dlg):
                        return dlg

                cur_url = ""
                try:
                    cur_url = self.driver.current_url or ""
                except Exception:
                    pass
                self._log(f"🔍 {log_tag} URL hiện tại: {cur_url}", "info")

                # Click any visible entry point (VN/EN)
                phrases = [
                    "bạn đang nghĩ gì", "ban dang nghi gi",
                    "thêm vào bài viết", "them vao bai viet",
                    "tạo bài viết", "tao bai viet",
                    "viết gì đó", "viet gi do",
                    "bạn viết gì đi", "ban viet gi di",
                    "viết bài", "viet bai",
                    "tạo bài viết trong nhóm", "tao bai viet trong nhom",
                    "what's on your mind", "create post",
                    "write something",
                ]
                for _try in range(6):
                    if _stop_requested() or self._is_action_blocked():
                        return None

                    # Strategy A: Find the SMALLEST (innermost) matching element –
                    # avoids clicking a huge parent div whose innerText also matches.
                    try:
                        clicked = bool(self.driver.execute_script(
                            _top_dialog_js_prelude()
                            + """
                            var phrases = arguments[0] || [];
                            function _vis(el){
                                try {
                                    if (!el) return false;
                                    var r = el.getBoundingClientRect();
                                    if (r.width < 5 || r.height < 5) return false;
                                    var st = window.getComputedStyle(el);
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    if (parseFloat(st.opacity || '1') <= 0.01) return false;
                                    return true;
                                } catch(e){ return false; }
                            }
                            function _matchPhrase(txt, attr){
                                txt = _norm(txt); attr = _norm(attr);
                                for (var i=0;i<phrases.length;i++){
                                    var p = _norm(phrases[i]);
                                    if (!p) continue;
                                    if ((txt && txt.indexOf(p) !== -1) || (attr && attr.indexOf(p) !== -1)) return true;
                                }
                                return false;
                            }
                            var selectors = '[role="button"], button, a, span, div[role], div[tabindex], div[class]';
                            var cands = Array.from(document.querySelectorAll(selectors));
                            var best = null;
                            var bestArea = Infinity;
                            for (var k=0;k<cands.length;k++){
                                var el = cands[k];
                                if (!_vis(el)) continue;
                                var t = _norm(el.innerText || el.textContent);
                                var a = _norm(el.getAttribute('aria-label') || '');
                                var ph = _norm(el.getAttribute('aria-placeholder') || el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || '');
                                if (!_matchPhrase(t, a) && !_matchPhrase(t, ph)) continue;
                                var r = el.getBoundingClientRect();
                                var area = r.width * r.height;
                                if (area < bestArea) { bestArea = area; best = el; }
                            }
                            if (best) {
                                try { best.scrollIntoView({block:'center'}); } catch(e) {}
                                try { best.click(); return true; } catch(e2) {}
                            }
                            return false;
                            """,
                            phrases,
                        ))
                    except Exception:
                        clicked = False

                    if clicked:
                        self._log(f"🔍 {log_tag} Đã click trigger (lần {_try+1}), chờ dialog...", "info")
                        dlg = _wait_top_dialog(timeout=10)
                        if dlg and _is_composer_dialog(dlg):
                            return dlg
                        self._log(f"🔍 {log_tag} Dialog chưa xuất hiện sau click, thử lại...", "info")
                    else:
                        if _try == 0:
                            self._log(f"🔍 {log_tag} Không tìm thấy trigger, thử lại...", "info")

                    # Strategy B (fallback): try Selenium XPath directly
                    if _try >= 2:
                        try:
                            from selenium.webdriver.common.by import By
                            xpaths = [
                                "//div[@role='button'][contains(., 'nghĩ gì')]",
                                "//div[@role='button'][contains(., 'nghi gi')]",
                                "//div[@role='button'][contains(., 'viết bài')]",
                                "//div[@role='button'][contains(., 'viet bai')]",
                                "//div[@role='button'][contains(., 'bạn viết')]",
                                "//div[@role='button'][contains(., 'ban viet')]",
                                "//span[contains(., 'nghĩ gì')]",
                                "//span[contains(., 'nghi gi')]",
                                "//*[@aria-label[contains(., 'Tạo bài viết')]]",
                                "//*[@aria-label[contains(., 'Create post')]]",
                                "//div[@role='button'][contains(., 'Viết gì đó')]",
                                "//div[@role='button'][contains(., 'viet gi do')]",
                            ]
                            for xp in xpaths:
                                try:
                                    els = self.driver.find_elements(By.XPATH, xp)
                                    for el in els:
                                        try:
                                            if el.is_displayed():
                                                el.click()
                                                self._log(f"🔍 {log_tag} Click trigger qua XPath (lần {_try+1})", "info")
                                                dlg = _wait_top_dialog(timeout=10)
                                                if dlg:
                                                    return dlg
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    time.sleep(1.0)
                return _wait_top_dialog(timeout=6)

            def _find_inline_editor():
                try:
                    return self.driver.execute_script(
                        """
                        function _vis(el){
                            try {
                                if (!el) return false;
                                var r = el.getBoundingClientRect();
                                if (r.width < 50 || r.height < 30) return false;
                                var st = window.getComputedStyle(el);
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                if (parseFloat(st.opacity || '1') <= 0.01) return false;
                                return true;
                            } catch(e){ return false; }
                        }
                        var cands = Array.from(document.querySelectorAll('[role="textbox"], [contenteditable="true"], [contenteditable="plaintext-only"]'));
                        for (var i=0;i<cands.length;i++){
                            var el = cands[i];
                            if (!_vis(el)) continue;
                            var a = (el.getAttribute('aria-label')||'').toLowerCase();
                            var p = (el.getAttribute('aria-placeholder')||el.getAttribute('data-placeholder')||'').toLowerCase();
                            if (a.indexOf('bình luận') !== -1 || a.indexOf('trả lời') !== -1 || a.indexOf('comment') !== -1 || a.indexOf('reply') !== -1 ||
                                p.indexOf('bình luận') !== -1 || p.indexOf('trả lời') !== -1 || p.indexOf('comment') !== -1 || p.indexOf('reply') !== -1) {
                                continue;
                            }
                            if (a.indexOf('bạn viết') !== -1 || a.indexOf('ban viet') !== -1 || a.indexOf('write') !== -1 ||
                                p.indexOf('bạn viết') !== -1 || p.indexOf('ban viet') !== -1 || p.indexOf('write') !== -1) {
                                return el;
                            }
                        }
                        return null;
                        """
                    )
                except Exception:
                    return None

            def _find_editor_in_dialog():
                """Find the contenteditable editor – search ALL dialogs AND the entire document.
                Uses relaxed visibility (≥2px) since the editor can be short initially."""
                try:
                    ed = self.driver.execute_script(
                        _top_dialog_js_prelude()
                        + """
                        function _edVis(el){
                            try {
                                if (!el) return false;
                                var r = el.getBoundingClientRect();
                                if (r.width < 2 || r.height < 2) return false;
                                var st = window.getComputedStyle(el);
                                if (st.display === 'none' || st.visibility === 'hidden') return false;
                                return true;
                            } catch(e){ return false; }
                        }

                        // Search scope: prefer dialogs; only fallback to document if no dialog exists.
                        var allDlgs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(_isVisible);
                        var scopes = allDlgs.length ? allDlgs : [document];

                        var selectors = [
                            '[role="textbox"][contenteditable="true"]',
                            '[role="textbox"][contenteditable="plaintext-only"]',
                            '[contenteditable="true"][aria-label]',
                            '[contenteditable="true"][data-placeholder]',
                            'div[contenteditable="true"]',
                            'div[contenteditable="plaintext-only"]',
                            'textarea',
                            'p[contenteditable="true"]',
                            'span[contenteditable="true"]',
                            '[contenteditable="true"]',
                            '[contenteditable="plaintext-only"]'
                        ];

                        var best = null;
                        var bestScore = -1;
                        var seen = new Set();

                        for (var sc=0; sc<scopes.length; sc++){
                            var scope = scopes[sc];
                            for (var si=0; si<selectors.length; si++){
                                var nodes;
                                try { nodes = Array.from(scope.querySelectorAll(selectors[si])); } catch(e) { continue; }
                                for (var i=0;i<nodes.length;i++){
                                    var el = nodes[i];
                                    if (seen.has(el)) continue;
                                    seen.add(el);
                                    if (!_edVis(el)) continue;
                                    var r = el.getBoundingClientRect();
                                    var area = Math.max(0, r.width) * Math.max(0, r.height);
                                    var a = _norm(el.getAttribute('aria-label') || '');
                                    var ph = _norm(el.getAttribute('data-placeholder') || '');
                                    var ap = _norm(el.getAttribute('aria-placeholder') || '');
                                    if (a.indexOf('bình luận') !== -1 || a.indexOf('trả lời') !== -1 || a.indexOf('comment') !== -1 || a.indexOf('reply') !== -1 ||
                                        ph.indexOf('bình luận') !== -1 || ph.indexOf('trả lời') !== -1 || ph.indexOf('comment') !== -1 || ph.indexOf('reply') !== -1 ||
                                        ap.indexOf('bình luận') !== -1 || ap.indexOf('trả lời') !== -1 || ap.indexOf('comment') !== -1 || ap.indexOf('reply') !== -1) {
                                        continue;
                                    }
                                    var score = area;
                                    if (
                                        a.indexOf('bạn đang nghĩ gì') !== -1 ||
                                        a.indexOf('ban dang nghi gi') !== -1 ||
                                        a.indexOf('nghĩ gì') !== -1 ||
                                        a.indexOf('nghi gi') !== -1 ||
                                        a.indexOf("what's on your mind") !== -1
                                    ) score += 1000000;
                                    if (
                                        a.indexOf('thêm vào bài viết') !== -1 ||
                                        a.indexOf('them vao bai viet') !== -1 ||
                                        a.indexOf('add to your post') !== -1
                                    ) score += 400000;
                                    if (
                                        ph.indexOf('bạn đang nghĩ gì') !== -1 ||
                                        ph.indexOf('ban dang nghi gi') !== -1 ||
                                        ph.indexOf('nghĩ gì') !== -1 ||
                                        ph.indexOf('nghi gi') !== -1 ||
                                        ph.indexOf("what's on your mind") !== -1 ||
                                        ap.indexOf('nghĩ gì') !== -1 ||
                                        ap.indexOf('nghi gi') !== -1 ||
                                        ap.indexOf("what's on your mind") !== -1
                                    ) score += 500000;
                                    if ((el.getAttribute('role')||'').toLowerCase() === 'textbox') score += 200000;
                                    if (score > bestScore){ bestScore = score; best = el; }
                                }
                            }
                        }
                        return best;
                        """
                    )
                    return ed
                except Exception:
                    return None

            def _bind_composer_root(editor):
                try:
                    root = self.driver.execute_script(
                        _top_dialog_js_prelude()
                        + """
                        var el = arguments[0];
                        if (!el) return null;
                        function _ok(box){
                            try {
                                if (!box || !_isVisible(box)) return false;
                                var t = _norm(box.innerText || box.textContent);
                                var hasComposerText = (
                                    t.indexOf('tạo bài viết') !== -1 ||
                                    t.indexOf('tao bai viet') !== -1 ||
                                    t.indexOf('create post') !== -1 ||
                                    t.indexOf('thêm vào bài viết') !== -1 ||
                                    t.indexOf('them vao bai viet') !== -1 ||
                                    t.indexOf('add to your post') !== -1
                                );
                                var hasEditor = !!box.querySelector('[role="textbox"], [contenteditable="true"], [contenteditable="plaintext-only"]');
                                return hasComposerText || hasEditor;
                            } catch(e){ return false; }
                        }
                        var dlg = el.closest('[role="dialog"]');
                        if (_ok(dlg)) return dlg;
                        var cur = el;
                        for (var i=0; i<12 && cur; i++) {
                            if (_ok(cur)) return cur;
                            cur = cur.parentElement;
                        }
                        return null;
                        """,
                        editor,
                    )
                    composer_root[0] = root
                except Exception:
                    composer_root[0] = None

            def _get_editor_text(editor):
                try:
                    return (self.driver.execute_script(
                        """
                        var el = arguments[0];
                        if (!el) return '';
                        if (el.tagName && el.tagName.toLowerCase() === 'textarea') return (el.value || '').trim();
                        return ((el.innerText || el.textContent || '') + '').trim();
                        """,
                        editor,
                    ) or "").strip()
                except Exception:
                    return ""

            def _set_editor_text(editor, value):
                """Set text in Facebook's React/Lexical editor using clipboard paste."""
                value = (value or "")
                if not editor:
                    return False

                from selenium.webdriver.common.action_chains import ActionChains
                import subprocess

                # Helper: put text to clipboard (Windows)
                def _set_clipboard(txt):
                    try:
                        process = subprocess.Popen(
                            ['clip.exe'], stdin=subprocess.PIPE, shell=True
                        )
                        process.communicate(txt.encode('utf-16-le'))
                    except Exception:
                        # Fallback: use tkinter clipboard
                        try:
                            import tkinter as _tk
                            _r = _tk.Tk()
                            _r.withdraw()
                            _r.clipboard_clear()
                            _r.clipboard_append(txt)
                            _r.update()
                            _r.destroy()
                        except Exception:
                            pass

                # Strategy 1: Click editor, clear, paste via Ctrl+V
                try:
                    # Click to focus
                    try:
                        ActionChains(self.driver).click(editor).perform()
                    except Exception:
                        try:
                            editor.click()
                        except Exception:
                            pass
                    time.sleep(0.3)

                    # Select all existing text and delete
                    try:
                        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
                        time.sleep(0.1)
                        ActionChains(self.driver).send_keys(Keys.DELETE).perform()
                        time.sleep(0.1)
                    except Exception:
                        pass

                    # Set clipboard and paste
                    _set_clipboard(value)
                    time.sleep(0.2)
                    ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(0.5)
                except Exception:
                    pass

                # Verify
                cur = _get_editor_text(editor)
                if value and value.strip()[:15] in cur:
                    return True

                # Strategy 2: JS execCommand insertText (fallback, safer than raw send_keys)
                try:
                    editor.click()
                    time.sleep(0.1)
                    self.driver.execute_script(
                        """
                        var el = arguments[0];
                        var val = arguments[1] || '';
                        try { el.focus(); } catch(e) {}
                        try {
                            var sel = window.getSelection();
                            if (sel) { sel.removeAllRanges(); }
                            var range = document.createRange();
                            range.selectNodeContents(el);
                            if (sel) sel.addRange(range);
                        } catch(e2) {}
                        try { document.execCommand('delete', false, null); } catch(e3) {}
                        try { document.execCommand('insertText', false, val); } catch(e4) {}
                        try {
                            el.dispatchEvent(new Event('input', {bubbles:true}));
                            el.dispatchEvent(new Event('keyup', {bubbles:true}));
                        } catch(e5) {}
                        """,
                        editor,
                        value,
                    )
                    time.sleep(0.3)
                except Exception:
                    pass

                cur = _get_editor_text(editor)
                return (not value) or (value.strip()[:10] in cur)

            def _click_in_top_dialog(texts, timeout=6, use_composer_scope=False):
                end = time.time() + timeout
                while time.time() < end and not _stop_requested():
                    if self._is_action_blocked():
                        return False
                    try:
                        clicked = bool(self.driver.execute_script(
                            _top_dialog_js_prelude()
                            + """
                            function _btnVis(el){
                                try {
                                    if (!el) return false;
                                    var r = el.getBoundingClientRect();
                                    if (r.width < 5 || r.height < 5) return false;
                                    var st = window.getComputedStyle(el);
                                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                                    if (parseFloat(st.opacity || '1') <= 0.01) return false;
                                    return true;
                                } catch(e){ return false; }
                            }
                            var texts = arguments[0] || [];
                            var root = arguments[1] || null;
                            // Restrict to active composer root when available.
                            var scopes = [];
                            if (root && root.isConnected && _isVisible(root)) {
                                scopes = [root];
                            } else {
                                var dlgs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(_isVisible);
                                scopes = dlgs;
                            }
                            if (!scopes.length) return false;
                            // Collect candidate buttons, prefer SMALLEST (innermost)
                            var candidates = [];
                            for (var s=0;s<scopes.length;s++){
                                var dlg = scopes[s];
                                var btns = Array.from(dlg.querySelectorAll('button, [role="button"], a[role="button"]'));
                                for (var i=0;i<btns.length;i++){
                                    var el = btns[i];
                                    if (!_btnVis(el)) continue;
                                    // Use DIRECT text content only (not deeply nested text)
                                    var directText = '';
                                    for (var c=0;c<el.childNodes.length;c++){
                                        var cn = el.childNodes[c];
                                        if (cn.nodeType === 3) directText += cn.textContent;
                                        else if (cn.nodeType === 1) {
                                            var ct = (cn.innerText||cn.textContent||'').trim();
                                            if (ct.length <= 30) directText += ct;
                                        }
                                    }
                                    directText = _norm(directText);
                                    // Also use full innerText but ONLY if it's short (<=30 chars)
                                    var fullText = _norm(el.innerText || el.textContent);
                                    var t = (fullText.length <= 30) ? fullText : directText;
                                    var a = _norm(el.getAttribute('aria-label') || '');
                                    var r = el.getBoundingClientRect();
                                    var area = r.width * r.height;
                                    for (var j=0;j<texts.length;j++){
                                        var n = _norm(texts[j]);
                                        if (!n) continue;
                                        var hit = (t && (t === n || t.indexOf(n) !== -1)) || (a && a.length <= 30 && (a === n || a.indexOf(n) !== -1));
                                        if (!hit) continue;
                                        if (!_isEnabled(el)) continue;
                                        candidates.push({el:el, area:area, exact: (t===n) ? 1 : 0});
                                    }
                                }
                            }
                            // Pick the best: prefer exact match, then smallest area
                            if (!candidates.length) return false;
                            candidates.sort(function(a,b){
                                if (b.exact !== a.exact) return b.exact - a.exact;
                                return a.area - b.area;
                            });
                            var best = candidates[0].el;
                            try { best.scrollIntoView({block:'center'}); } catch(e2) {}
                            try { best.click(); } catch(e3) { return false; }
                            return true;
                            """,
                            texts,
                            (composer_root[0] if use_composer_scope else None),
                        ))
                    except Exception:
                        clicked = False
                    if clicked:
                        return True
                    time.sleep(0.25)
                return False

            # 1) Open composer dialog
            self._log(f"📝 {log_tag} Mở hộp tạo bài viết...", "info")
            dlg = _open_composer_dialog()
            if not dlg:
                inline_editor = _find_inline_editor()
                if not inline_editor:
                    self._log(f"⚠️ {log_tag} Không mở được hộp tạo bài viết", "warn")
                    return False
                try:
                    composer_root[0] = inline_editor
                except Exception:
                    pass
            if self._is_action_blocked() or _stop_requested():
                return False

            # 2) Fill text (if any)
            if text:
                editor = None
                # Retry finding editor – it may take a moment to render
                for _ed_try in range(25):
                    if _stop_requested() or self._is_action_blocked():
                        break
                    editor = _find_editor_in_dialog()
                    if editor:
                        _bind_composer_root(editor)
                        break

                    # Diagnostic on first few tries
                    if _ed_try in (0, 3, 8):
                        try:
                            diag = self.driver.execute_script(
                                _top_dialog_js_prelude()
                                + """
                                var info = [];
                                // Count dialogs
                                var allDlgs = document.querySelectorAll('[role="dialog"]');
                                info.push('dialogs: ' + allDlgs.length);
                                for (var d=0;d<allDlgs.length;d++){
                                    var dl = allDlgs[d];
                                    var r = dl.getBoundingClientRect();
                                    info.push('  DLG['+d+']: w='+Math.round(r.width)+' h='+Math.round(r.height)+' z='+(window.getComputedStyle(dl).zIndex||'auto')+' vis='+(window.getComputedStyle(dl).visibility)+' heading='+(dl.querySelector('h2,h3,span')?(dl.querySelector('h2,h3,span').textContent||'').substring(0,40):''));
                                    var ces = dl.querySelectorAll('[contenteditable]');
                                    info.push('    CE: '+ces.length);
                                    var tbs = dl.querySelectorAll('[role="textbox"]');
                                    info.push('    TB: '+tbs.length);
                                }
                                // Global search
                                var gCE = document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]');
                                info.push('global CE: ' + gCE.length);
                                for (var i=0;i<Math.min(gCE.length,5);i++){
                                    var el = gCE[i];
                                    var r = el.getBoundingClientRect();
                                    info.push('  GCE['+i+']: tag='+el.tagName+' role='+(el.getAttribute('role')||'')+' w='+Math.round(r.width)+' h='+Math.round(r.height)+' label='+(el.getAttribute('aria-label')||'').substring(0,30));
                                }
                                var gTB = document.querySelectorAll('[role="textbox"]');
                                info.push('global TB: ' + gTB.length);
                                for (var i=0;i<Math.min(gTB.length,5);i++){
                                    var el = gTB[i];
                                    var r = el.getBoundingClientRect();
                                    info.push('  GTB['+i+']: tag='+el.tagName+' ce='+(el.getAttribute('contenteditable')||'null')+' w='+Math.round(r.width)+' h='+Math.round(r.height)+' label='+(el.getAttribute('aria-label')||'').substring(0,30));
                                }
                                return info.join('\\n');
                                """
                            )
                            self._log(f"🔍 {log_tag} Dialog DOM (try {_ed_try}):\n{diag}", "info")
                        except Exception as ex_diag:
                            self._log(f"🔍 {log_tag} Diag error: {ex_diag}", "warn")

                    # Try clicking inside dialog to activate the editor
                    if _ed_try <= 5:
                        try:
                            self.driver.execute_script(
                                _top_dialog_js_prelude()
                                + """
                                var dlg = _topDialog();
                                if (!dlg) return;
                                // Try multiple strategies to activate the editor area
                                var targets = [
                                    dlg.querySelector('[role="textbox"]'),
                                    dlg.querySelector('[contenteditable="true"]'),
                                    dlg.querySelector('[contenteditable="plaintext-only"]'),
                                    dlg.querySelector('[data-placeholder]'),
                                    dlg.querySelector('[aria-placeholder]'),
                                    dlg.querySelector('[aria-label*="nghĩ"]'),
                                    dlg.querySelector('[aria-label*="nghi"]'),
                                    dlg.querySelector('[aria-label*="mind"]'),
                                ];
                                for (var i=0;i<targets.length;i++){
                                    var el = targets[i];
                                    if (!el) continue;
                                    try { el.scrollIntoView({block:'center'}); } catch(e){}
                                    try { el.focus(); } catch(e){}
                                    try { el.click(); } catch(e){}
                                }
                                // Click small trigger text like "Bạn viết gì đi..." inside dialog
                                var phrases = ['bạn viết', 'ban viet', 'viết bài', 'viet bai', 'nghĩ gì', 'nghi gi', "what's on your mind"];
                                var nodes = dlg.querySelectorAll('div, span, p, a, button');
                                for (var k=0;k<nodes.length;k++){
                                    var n = nodes[k];
                                    var t = _norm(n.innerText || n.textContent);
                                    var a = _norm(n.getAttribute('aria-label') || '');
                                    var hit = false;
                                    for (var p=0;p<phrases.length;p++){
                                        var ph = _norm(phrases[p]);
                                        if ((t && t.indexOf(ph) !== -1) || (a && a.indexOf(ph) !== -1)) { hit = true; break; }
                                    }
                                    if (!hit) continue;
                                    try { n.scrollIntoView({block:'center'}); } catch(e){}
                                    try { n.click(); } catch(e){}
                                }
                                // Also try to click any paragraph-like area inside dialog
                                var ps = dlg.querySelectorAll('div, p, span');
                                for (var j=0;j<ps.length;j++){
                                    var el = ps[j];
                                    try {
                                        var t = (el.getAttribute('data-placeholder')||'').toLowerCase()
                                              + (el.getAttribute('aria-placeholder')||'').toLowerCase()
                                              + (el.getAttribute('aria-label')||'').toLowerCase();
                                        if (t.indexOf('ngh') !== -1 || t.indexOf('mind') !== -1) {
                                            el.click(); el.focus();
                                        }
                                    } catch(e){}
                                }
                                """
                            )
                        except Exception:
                            pass

                    # Also try Selenium click directly
                    if _ed_try in (2, 6, 10):
                        try:
                            from selenium.webdriver.common.by import By
                            for xp in [
                                "//div[@role='dialog']//div[@role='textbox']",
                                "//div[@role='dialog']//div[@contenteditable='true']",
                                "//div[@role='dialog']//div[@contenteditable]",
                                "//div[@role='dialog']//p[@role='textbox']",
                                "//div[@role='dialog']//*[contains(@aria-label,'nghĩ')]",
                                "//div[@role='dialog']//*[contains(@aria-label,'nghi')]",
                                "//div[@role='dialog']//*[contains(@data-placeholder,'nghĩ')]",
                            ]:
                                try:
                                    els = self.driver.find_elements(By.XPATH, xp)
                                    for el in els:
                                        try:
                                            if el.is_displayed():
                                                el.click()
                                                time.sleep(0.3)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    time.sleep(0.5)

                # Last resort: try to find ANY contenteditable on the page regardless of visibility
                if not editor:
                    try:
                        editor = self.driver.execute_script(
                            """
                            // Search in all dialogs first, then globally
                            var scopes = Array.from(document.querySelectorAll('[role="dialog"]'));
                            scopes.push(document);
                            for (var s=0;s<scopes.length;s++){
                                var el = scopes[s].querySelector('[role="textbox"]')
                                      || scopes[s].querySelector('[contenteditable="true"]')
                                      || scopes[s].querySelector('[contenteditable="plaintext-only"]')
                                      || scopes[s].querySelector('[contenteditable]');
                                if (el) return el;
                            }
                            return null;
                            """
                        )
                    except Exception:
                        editor = None

                if not editor:
                    self._log(f"⚠️ {log_tag} Không tìm thấy ô nhập nội dung trong dialog", "warn")
                else:
                    # Click/focus before typing
                    try:
                        editor.click()
                    except Exception:
                        pass
                    time.sleep(0.3)
                    ok_text = _set_editor_text(editor, text)
                    # Double-check what's actually in the editor
                    actual = _get_editor_text(editor)
                    if ok_text and actual and text.strip()[:10] in actual:
                        self._log(f"✍️ {log_tag} Đã nhập nội dung ({len(actual)} ký tự)", "ok")
                    else:
                        self._log(f"⚠️ {log_tag} Nhập nội dung có thể chưa thành công (actual: '{actual[:50]}...')", "warn")

            # 3) Attach image (if any)
            if img_path and os.path.isfile(img_path) and not _stop_requested() and not self._is_action_blocked():
                try:
                    file_input = self.driver.execute_script(
                        """
                        var root = arguments[0] || null;
                        var scopes = [];
                        if (root && root.isConnected) {
                            scopes = [root];
                        } else {
                            scopes = Array.from(document.querySelectorAll('[role="dialog"]'));
                        }
                        for (var s=0;s<scopes.length;s++){
                            var inp = scopes[s].querySelector('input[type="file"]');
                            if (inp) return inp;
                        }
                        return null;
                        """,
                        composer_root[0],
                    )
                except Exception:
                    file_input = None

                # Fallback: click "Ảnh/video" inside composer to reveal file input, then retry.
                if not file_input:
                    try:
                        _click_in_top_dialog(["ảnh/video", "anh/video", "photo/video", "photo", "ảnh", "anh"], timeout=1.0, use_composer_scope=True)
                        time.sleep(0.6)
                        file_input = self.driver.execute_script(
                            """
                            var root = arguments[0] || null;
                            var scopes = [];
                            if (root && root.isConnected) {
                                scopes = [root];
                            } else {
                                scopes = Array.from(document.querySelectorAll('[role="dialog"]'));
                            }
                            for (var s=0;s<scopes.length;s++){
                                var inp = scopes[s].querySelector('input[type="file"]');
                                if (inp) return inp;
                            }
                            return null;
                            """,
                            composer_root[0],
                        )
                    except Exception:
                        file_input = None
                if file_input:
                    try:
                        file_input.send_keys(img_path)
                        self._log(f"🖼️ {log_tag} Đã chọn ảnh, chờ tải lên...", "info")
                        for _ in range(60):
                            if _stop_requested() or self._is_action_blocked():
                                break
                            time.sleep(0.5)
                            try:
                                busy = bool(self.driver.execute_script(
                                    """
                                    var root = arguments[0] || null;
                                    var scopes = [];
                                    if (root && root.isConnected) {
                                        scopes = [root];
                                    } else {
                                        scopes = Array.from(document.querySelectorAll('[role="dialog"]'));
                                    }
                                    for (var s=0;s<scopes.length;s++){
                                        var p = scopes[s].querySelector('[role="progressbar"], [aria-label*="Đang tải" i], [aria-label*="Uploading" i]');
                                        if (p) return true;
                                    }
                                    return false;
                                    """,
                                    composer_root[0],
                                ))
                            except Exception:
                                busy = False
                            if not busy:
                                break
                        self._log(f"🖼️ {log_tag} Ảnh đã tải lên xong", "ok")
                    except Exception:
                        self._log(f"⚠️ {log_tag} Upload ảnh có thể thất bại", "warn")
                else:
                    self._log(f"⚠️ {log_tag} Không tìm thấy input file trong dialog", "warn")

            if self._is_action_blocked() or _stop_requested():
                return False

            # 4) Click flow: Next -> Post (handle VN/EN)
            # Facebook Page flow: composer → "Tiếp" (Next) → settings → "Đăng" (Post)
            time.sleep(1.0)  # Brief pause after image upload for UI to stabilize
            posted = False
            tiep_count = 0
            max_tiep = 2  # "Tiếp" should only need 1 click, 2 max
            dang_attempts = 0

            for _step in range(20):
                if self._is_action_blocked() or _stop_requested():
                    return False

                # Safety: if composer is gone, stop this run (avoid spilling actions into feed/comment areas).
                try:
                    dlg_count = int(self.driver.execute_script("return document.querySelectorAll('[role=\"dialog\"]').length;") or 0)
                except Exception:
                    dlg_count = 0

                if dlg_count == 0:
                    self._log(f"⚠️ {log_tag} Composer đã đóng trước khi bấm Tiếp/Đăng; dừng lượt này để tránh comment nhầm", "warn")
                    return False

                # Dismiss "Rời khỏi trang?" / "Leave page?" popups
                _click_in_top_dialog(["ở lại trang", "o lai trang", "stay on page", "ở lại", "stay"], timeout=0.3)
                # Dismiss "Lúc khác" / "Not now" popups
                _click_in_top_dialog(["lúc khác", "luc khac", "not now"], timeout=0.3)

                # Phase 1: Click "Tiếp" FIRST (required for Page composer)
                if tiep_count < max_tiep:
                    if _click_in_top_dialog(["tiếp", "tiep", "next", "tiếp tục", "tiep tuc", "continue"], timeout=1.2, use_composer_scope=True):
                        tiep_count += 1
                        self._log(f"➡️ {log_tag} Đã bấm Tiếp ({tiep_count}/{max_tiep})", "info")
                        time.sleep(3.5)  # Wait longer for Page composer to transition
                        continue

                # Phase 2: After "Tiếp", look for "Đăng"
                if tiep_count > 0 or _step >= 5:
                    if _click_in_top_dialog([
                        "đăng", "dang", "post",
                        "đăng ngay", "dang ngay",
                        "chia sẻ ngay", "chia se ngay",
                        "xuất bản", "xuat ban", "publish",
                        "lên lịch", "len lich", "schedule",
                    ], timeout=1.8, use_composer_scope=True):
                        self._log(f"📤 {log_tag} Đã bấm Đăng", "info")
                        posted = True
                        time.sleep(1.5)
                        break
                    dang_attempts += 1

                if _click_in_top_dialog(["lưu", "save"], timeout=0.5, use_composer_scope=True):
                    time.sleep(0.8)
                    continue

                # Diagnostic: log visible buttons periodically
                if _step % 5 == 4:
                    try:
                        btn_info = self.driver.execute_script(
                            """
                            var info = [];
                            var dlgs = Array.from(document.querySelectorAll('[role="dialog"]'));
                            info.push('dialogs: ' + dlgs.length);
                            // Always search ALL dialogs AND the full document
                            var scopes = dlgs.slice();
                            scopes.push(document);
                            var seen = new Set();
                            for (var s=0;s<scopes.length;s++){
                                var btns = scopes[s].querySelectorAll('button, [role="button"]');
                                for (var i=0;i<btns.length;i++){
                                    var el = btns[i];
                                    if (seen.has(el)) continue;
                                    seen.add(el);
                                    var r = el.getBoundingClientRect();
                                    if (r.width < 5 || r.height < 5) continue;
                                    var st = window.getComputedStyle(el);
                                    if (st.display === 'none' || st.visibility === 'hidden') continue;
                                    var t = (el.innerText||el.textContent||'').trim();
                                    if (!t || t.length > 60) continue;
                                    var a = (el.getAttribute('aria-label')||'').substring(0,30);
                                    var dis = el.getAttribute('disabled')!==null || (el.getAttribute('aria-disabled')||'')==='true';
                                    info.push('  [s'+s+'] "'+t.substring(0,30)+'" lbl="'+a+'" dis='+dis+' '+Math.round(r.width)+'x'+Math.round(r.height));
                                }
                            }
                            if (info.length <= 1) info.push('  (no buttons found)');
                            return info.join('\\n');
                            """
                        )
                        self._log(f"🔍 {log_tag} Buttons (step {_step}):\n{btn_info}", "info")
                    except Exception:
                        pass

                time.sleep(0.8)

            # Give Facebook time to submit and close the composer by itself.
            # Also dismiss any "Lúc khác" / "Not now" popups that appear after clicking Đăng
            if posted and not _stop_requested() and not self._is_action_blocked():
                for _wait_step in range(30):
                    if _stop_requested() or self._is_action_blocked():
                        break
                    # Try to dismiss "Lúc khác" popup that may appear after Đăng
                    _click_in_top_dialog(["lúc khác", "luc khac", "not now", "bỏ qua", "bo qua", "skip"], timeout=0.3)
                    try:
                        still_open = bool(self.driver.execute_script(_top_dialog_js_prelude() + "return !!_topDialog();"))
                    except Exception:
                        still_open = False
                    if not still_open:
                        break
                    time.sleep(0.5)

            try:
                if posted:
                    self._close_all_dialogs(aggressive=True)
            except Exception:
                pass

            if self._is_action_blocked() or _stop_requested():
                return False
            return posted
        except Exception as e:
            try:
                self._log(f"❌ {log_tag} Lỗi khi đăng: {e}", "err")
            except Exception:
                pass
            return False

    # ── Tab 1: Tự động ────────────────────────────────────────────────────────
    def _build_tab_auto(self, parent):
        # ─ Quy tắc thay thế ─
        rf = tk.LabelFrame(parent, text="  Quy tắc thay thế văn bản  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        rf.pack(fill="x", padx=14, pady=(10, 6))

        tk.Label(rf, text="Nhập các cặp văn bản cần TÌM và THAY THẾ (mỗi dòng 1 cặp, cách nhau bởi ' => '):",
                 font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(anchor="w", padx=14, pady=(8, 4))
        
        tk.Label(rf, text="Ví dụ:  Làm luận văn => Hỗ Trợ luận văn",
                 font=FONT, bg=BG_DARK, fg=YELLOW, anchor="w").pack(anchor="w", padx=30, pady=(0, 6))

        self.rules_text = scrolledtext.ScrolledText(rf, font=FONT_M, height=4,
                                                     bg=BG_PANEL, fg=FG_LIGHT,
                                                     insertbackground=FG_LIGHT,
                                                     relief="flat", wrap="word")
        self.rules_text.pack(fill="x", padx=14, pady=(0, 8))
        
        # Giá trị mặc định
        self.rules_text.insert("1.0", "Làm luận văn => Hỗ Trợ luận văn")

        # ─ Login frame ─
        lf = tk.LabelFrame(parent, text="  Đăng nhập Facebook  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        lf.pack(fill="x", padx=14, pady=(10, 6))

        # Hướng dẫn
        tk.Label(lf,
                 text="Nhấn «Mở Chrome & Đăng nhập» → Đăng nhập Facebook trong cửa sổ Chrome → "
                      "Quay l",
                 font=FONT, bg=BG_DARK, fg=FG_MUTED, wraplength=800, justify="left"
                 ).pack(anchor="w", padx=14, pady=(8, 6))

        row0 = tk.Frame(lf, bg=BG_DARK)
        row0.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_login = self._btn(row0, "🌐  Mở Chrome & Đăng nhập", self._do_login, ACCENT)
        self.btn_login.pack(side="left", padx=(0, 10))


        self.lbl_login_status = tk.Label(lf, text="●  Chưa đăng nhập",
                                          font=FONT_B, bg=BG_DARK, fg=FG_MUTED)
        self.lbl_login_status.pack(anchor="w", padx=14, pady=(0, 6))

        # ─ Action frame ─
        af = tk.LabelFrame(parent, text="  Tự động tải & sửa bài đăng  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        af.pack(fill="x", padx=14, pady=6)

        arow = tk.Frame(af, bg=BG_DARK)
        arow.pack(fill="x", padx=10, pady=8)

        tk.Label(arow, text="Số bài tải:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        self.spin_count = tk.Spinbox(arow, from_=1, to=200, width=5,
                                     font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                                     buttonbackground=BG_CARD, relief="flat")
        self.spin_count.delete(0, "end"); self.spin_count.insert(0, "20")
        self.spin_count.pack(side="left", padx=(6, 12))

        # Checkbox: Quét đến hết trang
        self.var_scan_all = tk.BooleanVar(value=False)
        self.chk_scan_all = tk.Checkbutton(arow, text="Quét đến hết trang",
                                            variable=self.var_scan_all,
                                            font=FONT, bg=BG_DARK, fg=FG_LIGHT,
                                            activebackground=BG_DARK, activeforeground=ACCENT,
                                            selectcolor=BG_DARK)
        self.chk_scan_all.pack(side="left", padx=(0, 20))

        self.btn_auto = self._btn(arow, "⚡  Quét & Sửa tự động", self._do_auto_fix, ACCENT)
        self.btn_auto.pack(side="left", padx=(0, 8))
        self.btn_stop = self._btn(arow, "⏹  Dừng", self._do_stop, "#2d2d44")
        self.btn_stop.pack(side="left")

        style2 = ttk.Style()
        style2.configure("TProgressbar", troughcolor=BG_PANEL,
                         background=ACCENT, thickness=8)
        self.progress = ttk.Progressbar(af, mode="determinate", length=400)
        self.progress.pack(padx=14, pady=(0, 8), fill="x")

        # ─ Log ─
        tk.Label(parent, text="📋  Nhật ký hoạt động & danh sách bài đăng",
                 font=FONT_B, bg=BG_DARK, fg=FG_MUTED, anchor="w"
                 ).pack(anchor="w", padx=14, pady=(6, 2))

        self.log_box = scrolledtext.ScrolledText(parent, font=FONT_M, height=14,
                                                  bg=BG_PANEL, fg=FG_LIGHT,
                                                  insertbackground=FG_LIGHT,
                                                  relief="flat", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.log_box.tag_config("ok",   foreground=GREEN)
        self.log_box.tag_config("warn", foreground=YELLOW)
        self.log_box.tag_config("err",  foreground=ACCENT)
        self.log_box.tag_config("info", foreground=FG_MUTED)


    def _auto_login_on_start(self):
        """Tự động mở Chrome & kiểm tra đăng nhập khi mới mở app.

        Chỉ chạy một lần, nếu đã có driver hoặc đã đăng nhập thì bỏ qua.
        Người dùng vẫn có thể bấm nút đăng nhập thủ công như trước.
        """
        try:
            if self.logged_in or self.driver or self._auto_login_started:
                return
            self._auto_login_started = True
            self._log("🔄  Tự động mở Chrome & kiểm tra đăng nhập Facebook...", "info")
            self._do_login()
        except Exception:
            # Không để lỗi auto login làm crash app
            self._auto_login_started = False


    # ── Tab 2: Auto Comment Nhóm ──────────────────────────────────────────────
    def _build_tab_comment(self, parent):
        # ─ Top Control Row - ALL ACTION BUTTONS HERE ─
        top_control = tk.Frame(parent, bg=BG_DARK)
        top_control.pack(fill="x", padx=14, pady=(10, 6))
        
        # Left side: Group management buttons
        left_btns = tk.Frame(top_control, bg=BG_DARK)
        left_btns.pack(side="left")
        
        self._btn(left_btns, "🔄  Tải nhóm", self._fetch_groups, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☑️  Chọn tất cả", lambda: self._toggle_all_groups(True), "#6ab04c").pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☐  Bỏ chọn", lambda: self._toggle_all_groups(False), "#2d2d44").pack(side="left")
        
        # Right side: Main action buttons
        right_btns = tk.Frame(top_control, bg=BG_DARK)
        right_btns.pack(side="right")
        
        self.btn_start_comment = self._btn(right_btns, "▶️  Bắt đầu", self._start_commenting, ACCENT)
        self.btn_start_comment.pack(side="left", padx=(0, 6))
        
        self.btn_stop_comment = self._btn(right_btns, "⏹  Dừng", self._stop_commenting, "#e74c3c")
        self.btn_stop_comment.pack(side="left", padx=(0, 6))
        
        self._btn(right_btns, "💾  Lưu", self._save_comment_config, "#6ab04c").pack(side="left")

        # ─ Group Selection ─
        gf = tk.LabelFrame(parent, text="  Chọn nhóm Facebook  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        gf.pack(fill="x", padx=14, pady=(4, 6))

        # Quick search
        search_row = tk.Frame(gf, bg=BG_DARK)
        search_row.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(search_row, text="Tìm nhanh:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        search_entry = tk.Entry(
            search_row,
            textvariable=self.comment_group_search_var,
            font=FONT,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            relief="flat",
        )
        search_entry.pack(side="left", padx=(8, 6), fill="x", expand=True)
        tk.Button(
            search_row,
            text="Xoá",
            font=FONT_B,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            activebackground=BG_CARD,
            activeforeground=FG_LIGHT,
            relief="flat",
            cursor="hand2",
            command=lambda: self.comment_group_search_var.set(""),
        ).pack(side="left")

        # Scrollable group list - FIXED HEIGHT
        group_canvas_frame = tk.Frame(gf, bg=BG_DARK)
        group_canvas_frame.pack(fill="x", padx=10, pady=(4, 8))
        
        group_canvas = tk.Canvas(group_canvas_frame, bg=BG_PANEL, highlightthickness=0, height=200)  # Reduced height
        group_scrollbar = tk.Scrollbar(group_canvas_frame, orient="vertical", command=group_canvas.yview)
        self.group_list_frame = tk.Frame(group_canvas, bg=BG_PANEL)
        
        group_canvas.create_window((0, 0), window=self.group_list_frame, anchor="nw")
        group_canvas.configure(yscrollcommand=group_scrollbar.set)
        
        group_canvas.pack(side="left", fill="both", expand=True)
        group_scrollbar.pack(side="right", fill="y")
        
        def _on_group_frame_configure(event):
            group_canvas.configure(scrollregion=group_canvas.bbox("all"))
        self.group_list_frame.bind("<Configure>", _on_group_frame_configure)

        try:
            self.comment_group_search_var.trace_add("write", lambda *_: self._apply_comment_group_filter())
        except Exception:
            pass

        self.lbl_comment_selected = tk.Label(
            gf,
            textvariable=self.comment_selected_count_var,
            font=FONT,
            bg=BG_DARK,
            fg=FG_MUTED,
            anchor="w",
        )
        self.lbl_comment_selected.pack(fill="x", padx=12, pady=(0, 4))

        # ─ Bottom split layout (scrollable) ─
        bottom_wrap = tk.Frame(parent, bg=BG_DARK)
        bottom_wrap.pack(fill="both", expand=True, padx=14, pady=(4, 6))

        bottom_canvas = tk.Canvas(bottom_wrap, bg=BG_DARK, highlightthickness=0)
        bottom_scroll = tk.Scrollbar(bottom_wrap, orient="vertical", command=bottom_canvas.yview)
        bottom_canvas.configure(yscrollcommand=bottom_scroll.set)

        bottom_scroll.pack(side="right", fill="y")
        bottom_canvas.pack(side="left", fill="both", expand=True)

        bottom = tk.Frame(bottom_canvas, bg=BG_DARK)
        bottom_canvas.create_window((0, 0), window=bottom, anchor="nw")

        def _on_bottom_configure(_e=None):
            try:
                bottom_canvas.configure(scrollregion=bottom_canvas.bbox("all"))
            except Exception:
                pass

        def _on_bottom_mousewheel(e):
            try:
                bottom_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass

        bottom.bind("<Configure>", _on_bottom_configure)
        bottom_canvas.bind_all("<MouseWheel>", _on_bottom_mousewheel)

        left_col = tk.Frame(bottom, bg=BG_DARK)
        right_col = tk.Frame(bottom, bg=BG_DARK)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right_col.pack(side="left", fill="both", expand=True)

        # Left: comment content
        cf = tk.LabelFrame(left_col, text="  Nội dung comment  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        cf.pack(fill="both", expand=True)

        tk.Label(cf, text="Nội dung comment (5 ô, dán nội dung dài vào từng ô):", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(anchor="w", padx=14, pady=(6, 2))

        self.comment_textboxes = []
        for idx in range(5):
            row = tk.Frame(cf, bg=BG_DARK)
            row.pack(fill="x", padx=14, pady=(0, 4))
            tk.Label(row, text=f"Mẫu {idx+1}:", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(anchor="w")
            box = scrolledtext.ScrolledText(
                row,
                font=FONT_M,
                height=4,
                bg=BG_PANEL,
                fg=FG_LIGHT,
                insertbackground=FG_LIGHT,
                relief="flat",
                wrap="word",
            )
            box.pack(fill="x", pady=(2, 2))
            self.comment_textboxes.append(box)

        # Right: images
        imgf = tk.LabelFrame(right_col, text="  Ảnh đính kèm  ",
                             font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        imgf.pack(fill="x", pady=(0, 6))

        img_row = tk.Frame(imgf, bg=BG_DARK)
        img_row.pack(fill="x", padx=14, pady=(6, 6))

        tk.Label(img_row, text="Ảnh:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(0, 10))
        self._btn(img_row, "📁  Chọn ảnh", self._choose_image, "#6ab04c").pack(side="left", padx=(0, 10))
        self._btn(img_row, "➕  Thêm ảnh", self._append_image_to_list, "#6ab04c").pack(side="left", padx=(0, 10))
        self._btn(img_row, "✖", lambda: self.comment_image_path.set(""), "#2d2d44").pack(side="right")

        self.img_path_label = tk.Label(imgf, textvariable=self.comment_image_path, font=("Segoe UI", 9),
                                        bg=BG_DARK, fg=FG_MUTED, anchor="w")
        self.img_path_label.pack(fill="x", padx=14, pady=(0, 6))

        tk.Label(imgf, text="Danh sách ảnh (mỗi dòng 1 file):", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(anchor="w", padx=14)
        self.comment_images_box = scrolledtext.ScrolledText(
            imgf,
            font=FONT_M,
            height=4,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            insertbackground=FG_LIGHT,
            relief="flat",
            wrap="word",
        )
        self.comment_images_box.pack(fill="x", padx=14, pady=(2, 2))
        self._btn(imgf, "🧹  Xóa danh sách ảnh", self._clear_image_list, "#2d2d44").pack(anchor="e", padx=14, pady=(0, 6))

        # ─ Execution Strategy ─
        sf = tk.LabelFrame(right_col, text="  Chiến lược thực thi  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        sf.pack(fill="both", expand=True)

        opt_row = tk.Frame(sf, bg=BG_DARK)
        opt_row.pack(fill="x", padx=14, pady=(6, 2))
        tk.Checkbutton(
            opt_row,
            text="Biến thể nhỏ",
            variable=self.comment_use_variation_var,
            font=FONT,
            bg=BG_DARK,
            fg=FG_LIGHT,
            activebackground=BG_DARK,
            activeforeground=ACCENT,
            selectcolor=BG_DARK,
        ).pack(anchor="w")

        delay_row = tk.Frame(sf, bg=BG_DARK)
        delay_row.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(delay_row, text="Nghỉ giữa comment:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Label(delay_row, text="từ", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(6, 4))
        tk.Spinbox(delay_row, from_=0, to=300, textvariable=self.comment_delay_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(delay_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(2, 4))
        tk.Spinbox(delay_row, from_=0, to=300, textvariable=self.comment_delay_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(delay_row, text="giây", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        group_rest_row = tk.Frame(sf, bg=BG_DARK)
        group_rest_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(group_rest_row, text="Nghỉ sau mỗi nhóm:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Label(group_rest_row, text="từ", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(6, 4))
        tk.Spinbox(group_rest_row, from_=0, to=30, textvariable=self.comment_group_rest_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(group_rest_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(2, 4))
        tk.Spinbox(group_rest_row, from_=0, to=30, textvariable=self.comment_group_rest_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(group_rest_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        session_row = tk.Frame(sf, bg=BG_DARK)
        session_row.pack(fill="x", padx=14, pady=(2, 2))
        tk.Label(session_row, text="Giới hạn nhóm/phiên:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Label(session_row, text="từ", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(6, 4))
        tk.Spinbox(session_row, from_=1, to=200, textvariable=self.comment_session_group_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(session_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(2, 4))
        tk.Spinbox(session_row, from_=1, to=200, textvariable=self.comment_session_group_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(session_row, text="nhóm", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        session_rest_row = tk.Frame(sf, bg=BG_DARK)
        session_rest_row.pack(fill="x", padx=14, pady=(2, 6))
        tk.Label(session_rest_row, text="Nghỉ giữa các phiên:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Label(session_rest_row, text="từ", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(6, 4))
        tk.Spinbox(session_rest_row, from_=5, to=240, textvariable=self.comment_session_rest_min_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(session_rest_row, text="đến", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left", padx=(2, 4))
        tk.Spinbox(session_rest_row, from_=5, to=240, textvariable=self.comment_session_rest_max_var, width=5,
                   font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                   buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(session_rest_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        # Post count selection (compact)
        post_count_row = tk.Frame(sf, bg=BG_DARK)
        post_count_row.pack(fill="x", padx=14, pady=(6, 3))  # Reduced padding
        
        tk.Checkbutton(post_count_row,
                   text="Comment bài cũ khi bấm Bắt đầu",
                   variable=self.comment_old_posts_var,
                   font=FONT, bg=BG_DARK, fg=FG_LIGHT,
                   activebackground=BG_DARK, activeforeground=ACCENT,
                   selectcolor=BG_DARK).pack(side="left", padx=(0, 12))

        tk.Label(post_count_row, text="Số bài cũ:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left", padx=(0, 8))
        tk.Spinbox(post_count_row, from_=1, to=50, textvariable=self.comment_post_count, width=5,
                  font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                  buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(0, 6))
        tk.Label(post_count_row, text="bài/nhóm", font=FONT, bg=BG_DARK, fg=FG_MUTED).pack(side="left")

        strat_row = tk.Frame(sf, bg=BG_DARK)
        strat_row.pack(fill="x", padx=14, pady=(2, 4))  # Reduced padding
        
        tk.Radiobutton(strat_row, text="Tuần tự (1 tab, ổn định)", variable=self.comment_mode_var, 
                      value="sequential", font=FONT, bg=BG_DARK, fg=FG_LIGHT,
                      activebackground=BG_DARK, activeforeground=ACCENT,
                      selectcolor=BG_DARK).pack(anchor="w")
        
        tk.Radiobutton(strat_row, text="Song song (nhiều tabs, nhanh hơn)", variable=self.comment_mode_var,
                      value="parallel", font=FONT, bg=BG_DARK, fg=FG_LIGHT,
                      activebackground=BG_DARK, activeforeground=ACCENT,
                      selectcolor=BG_DARK).pack(anchor="w")

        # ─ Monitor Mode ─
        mon_row = tk.Frame(sf, bg=BG_DARK)
        mon_row.pack(fill="x", padx=14, pady=(0, 6))  # Reduced padding
        
        self.chk_monitor = tk.Checkbutton(mon_row, text="Auto-comment bài mới (monitor mode)",
                                          variable=self.monitor_enabled_var,
                                          font=FONT, bg=BG_DARK, fg=FG_LIGHT,
                                          activebackground=BG_DARK, activeforeground=ACCENT,
                                          selectcolor=BG_DARK)
        self.chk_monitor.pack(side="left", padx=(0, 10))
        
        tk.Label(mon_row, text="Check mỗi:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(mon_row, from_=1, to=60, textvariable=self.monitor_interval_var, width=5,
                  font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                  buttonbackground=BG_CARD, relief="flat").pack(side="left", padx=(6, 6))
        tk.Label(mon_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")


    # ── Tab 4: Auto duyệt bài nhóm ───────────────────────────────────────────
    def _build_tab_group_approval(self, parent):
        # Top control row
        top_control = tk.Frame(parent, bg=BG_DARK)
        top_control.pack(fill="x", padx=14, pady=(10, 6))

        # Left: group actions
        left_btns = tk.Frame(top_control, bg=BG_DARK)
        left_btns.pack(side="left")

        self._btn(left_btns, "🔄  Tải nhóm", self._fetch_groups_for_approval, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☑️  Chọn tất cả", lambda: self._toggle_all_approval_groups(True), "#6ab04c").pack(side="left", padx=(0, 6))
        self._btn(left_btns, "☐  Bỏ chọn", lambda: self._toggle_all_approval_groups(False), "#2d2d44").pack(side="left")

        # Right: start/stop + save
        right_btns = tk.Frame(top_control, bg=BG_DARK)
        right_btns.pack(side="right")

        self.btn_start_approval = self._btn(right_btns, "▶️  Bắt đầu", self._start_group_approval, ACCENT)
        self.btn_start_approval.pack(side="left", padx=(0, 6))

        self.btn_stop_approval = self._btn(right_btns, "⏹  Dừng", self._stop_group_approval, "#e74c3c")
        self.btn_stop_approval.pack(side="left", padx=(0, 6))

        self._btn(right_btns, "💾  Lưu", self._save_approval_config, "#6ab04c").pack(side="left")
        self._set_run_buttons(self.btn_start_approval, self.btn_stop_approval, False, ACCENT, "#e74c3c")

        # Group selection
        gf = tk.LabelFrame(parent, text="  Chọn nhóm Facebook (hãy chọn các nhóm bạn là quản trị viên)  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        gf.pack(fill="x", padx=14, pady=(4, 6))

        group_canvas_frame = tk.Frame(gf, bg=BG_DARK)
        group_canvas_frame.pack(fill="x", padx=10, pady=(4, 8))

        group_canvas = tk.Canvas(group_canvas_frame, bg=BG_PANEL, highlightthickness=0, height=200)
        group_scrollbar = tk.Scrollbar(group_canvas_frame, orient="vertical", command=group_canvas.yview)
        self.approval_group_list_frame = tk.Frame(group_canvas, bg=BG_PANEL)

        group_canvas.create_window((0, 0), window=self.approval_group_list_frame, anchor="nw")
        group_canvas.configure(yscrollcommand=group_scrollbar.set)

        group_canvas.pack(side="left", fill="both", expand=True)
        group_scrollbar.pack(side="right", fill="y")

        def _on_group_frame_configure(event):
            group_canvas.configure(scrollregion=group_canvas.bbox("all"))

        self.approval_group_list_frame.bind("<Configure>", _on_group_frame_configure)

        # Criteria
        cf = tk.LabelFrame(parent, text="  Tiêu chí tự động từ chối / phê duyệt  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        cf.pack(fill="x", padx=14, pady=(4, 4))

        tk.Label(cf, text="Danh sách từ khoá nghi lừa đảo / vi phạm (mỗi dòng 1 từ/ký tự):",
                 font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(anchor="w", padx=14, pady=(6, 2))

        self.approval_keywords_box = scrolledtext.ScrolledText(
            cf,
            font=FONT_M,
            height=4,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            insertbackground=FG_LIGHT,
            relief="flat",
            wrap="word",
        )
        self.approval_keywords_box.pack(fill="x", padx=14, pady=(0, 6))

        tk.Label(cf,
                 text="Ví dụ: đa cấp, vay tiền, đầu tư lợi nhuận cao, cho vay nóng...",
                 font=FONT, bg=BG_DARK, fg=YELLOW).pack(anchor="w", padx=18, pady=(0, 4))

        opt_row = tk.Frame(cf, bg=BG_DARK)
        opt_row.pack(fill="x", padx=14, pady=(0, 6))

        tk.Checkbutton(
            opt_row,
            text="Tự động PHÊ DUYỆT các bài không chứa từ khoá xấu",
            variable=self.approval_auto_approve_safe,
            font=FONT,
            bg=BG_DARK,
            fg=FG_LIGHT,
            activebackground=BG_DARK,
            activeforeground=ACCENT,
            selectcolor=BG_DARK,
        ).pack(anchor="w")

        # Schedule
        sf = tk.LabelFrame(parent, text="  Lịch quét & duyệt bài  ",
                           font=FONT_B, bg=BG_DARK, fg=FG_MUTED, bd=1, relief="groove")
        sf.pack(fill="x", padx=14, pady=(4, 6))

        mode_row = tk.Frame(sf, bg=BG_DARK)
        mode_row.pack(fill="x", padx=14, pady=(6, 2))

        tk.Radiobutton(
            mode_row,
            text="Chạy 1 lần (ngay bây giờ)",
            variable=self.approval_mode_var,
            value="once",
            font=FONT,
            bg=BG_DARK,
            fg=FG_LIGHT,
            activebackground=BG_DARK,
            activeforeground=ACCENT,
            selectcolor=BG_DARK,
        ).pack(anchor="w")

        tk.Radiobutton(
            mode_row,
            text="Lặp lại, quét bài chờ duyệt theo chu kỳ",
            variable=self.approval_mode_var,
            value="interval",
            font=FONT,
            bg=BG_DARK,
            fg=FG_LIGHT,
            activebackground=BG_DARK,
            activeforeground=ACCENT,
            selectcolor=BG_DARK,
        ).pack(anchor="w")

        interval_row = tk.Frame(sf, bg=BG_DARK)
        interval_row.pack(fill="x", padx=14, pady=(0, 6))

        tk.Label(interval_row, text="Chu kỳ quét:", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")
        tk.Spinbox(
            interval_row,
            from_=1,
            to=120,
            textvariable=self.approval_interval_var,
            width=5,
            font=FONT,
            bg=BG_PANEL,
            fg=FG_LIGHT,
            buttonbackground=BG_CARD,
            relief="flat",
        ).pack(side="left", padx=(6, 6))
        tk.Label(interval_row, text="phút", font=FONT, bg=BG_DARK, fg=FG_LIGHT).pack(side="left")


    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════
    def _get_appdata_dir(self):
        """Return config/cache directory under AppData Roaming and ensure it exists."""
        try:
            base = os.path.dirname(__file__)
            path = os.path.join(base, "FBTextFixerData")
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            return os.path.dirname(__file__)

    def _btn(self, parent, text, cmd, bg):
        return tk.Button(parent, text=text, command=cmd,
                         font=FONT_B, bg=bg, fg=FG_LIGHT,
                         activebackground=BG_PANEL, activeforeground=FG_LIGHT,
                         relief="flat", cursor="hand2", padx=14, pady=5)

    def _set_run_buttons(self, start_btn, stop_btn, running, start_bg, stop_bg):
        if not start_btn or not stop_btn:
            return
        if running:
            start_btn.configure(state="disabled", bg=BG_PANEL)
            stop_btn.configure(state="normal", bg=stop_bg)
        else:
            start_btn.configure(state="normal", bg=start_bg)
            stop_btn.configure(state="disabled", bg=BG_PANEL)

    def _strip_links(self, text):
        if not text:
            return ""
        t = re.sub(r"https?://\S+", "", text)
        t = re.sub(r"www\.\S+", "", t)
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        return "\n".join(lines).strip()

    def _strip_phones(self, text):
        if not text:
            return ""
        t = re.sub(r"\+?\d[\d\s\-\(\)]{7,}\d", "", text)
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        return "\n".join(lines).strip()

    def _sanitize_text_for_pending(self, text):
        return self._strip_phones(self._strip_links(text))

    def _detect_pending_comment(self, post_el):
        try:
            phrases = [
                "đang chờ",
                "chờ phê duyệt",
                "chờ xét duyệt",
                "pending",
                "awaiting",
                "awaiting approval",
                "pending approval",
                "needs approval",
                "dang cho",
                "cho phe duyet",
                "cho xet duyet",
            ]
            return self.driver.execute_script(
                """
                var post = arguments[0];
                var phrases = arguments[1] || [];
                if (!post) return '';
                function norm(s){
                    try { return (s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
                    catch(e){ return (s||'').toLowerCase(); }
                }
                function hasPhrase(t){
                    var n = norm(t);
                    for (var i=0;i<phrases.length;i++) {
                        if (n.indexOf(norm(phrases[i])) !== -1) return phrases[i];
                    }
                    return '';
                }

                var text = (post.innerText || post.textContent || '');
                var hit = hasPhrase(text);
                if (hit) return hit;

                function scanNodes(nodes, limit){
                    for (var j=0; j<nodes.length && j<limit; j++) {
                        var t = nodes[j].innerText || nodes[j].textContent || '';
                        var hit = hasPhrase(t);
                        if (hit) return hit;

                        var a = nodes[j].getAttribute && (nodes[j].getAttribute('aria-label') || '');
                        hit = hasPhrase(a || '');
                        if (hit) return hit;
                    }
                    return '';
                }

                // Check status-like elements inside the post
                var nodes = post.querySelectorAll('[role="status"], [role="alert"], span, div, a, button');
                var hit2 = scanNodes(nodes, 200);
                if (hit2) return hit2;

                // Check nearby elements around the post card (comment status may render outside)
                var pr = post.getBoundingClientRect();
                var all = Array.from(document.querySelectorAll('span, div, a, button'));
                var nearby = [];
                for (var k=0; k<all.length && nearby.length < 200; k++) {
                    var el = all[k];
                    if (!el || !el.getBoundingClientRect) continue;
                    var r = el.getBoundingClientRect();
                    var cx = r.left + r.width/2;
                    var cy = r.top + r.height/2;
                    var xOK = (cx >= (pr.left - 80)) && (cx <= (pr.right + 80));
                    var yOK = (cy >= (pr.top - 40)) && (cy <= (pr.bottom + 160));
                    if (xOK && yOK) nearby.push(el);
                }
                var hit3 = scanNodes(nearby, 200);
                if (hit3) return hit3;

                // Check vicinity of focused element (comment box often keeps focus)
                try {
                    var ae = document.activeElement;
                    if (ae && ae.getBoundingClientRect) {
                        var ar = ae.getBoundingClientRect();
                        var aAll = Array.from(document.querySelectorAll('span, div, a, button'));
                        var around = [];
                        for (var m=0; m<aAll.length && around.length < 200; m++) {
                            var el2 = aAll[m];
                            if (!el2 || !el2.getBoundingClientRect) continue;
                            var r2 = el2.getBoundingClientRect();
                            var cx2 = r2.left + r2.width/2;
                            var cy2 = r2.top + r2.height/2;
                            var x2 = (cx2 >= (ar.left - 120)) && (cx2 <= (ar.right + 120));
                            var y2 = (cy2 >= (ar.top - 80)) && (cy2 <= (ar.bottom + 200));
                            if (x2 && y2) around.push(el2);
                        }
                        var hit4 = scanNodes(around, 200);
                        if (hit4) return hit4;
                    }
                } catch(e) {}
                return '';
                """,
                post_el,
                phrases,
            ) or ""
        except Exception:
            return ""

    def _detect_rejected_comment(self, post_el):
        try:
            phrases = [
                "bình luận đã bị từ chối",
                "tự động từ chối bình luận",
                "bị từ chối",
                "đã bị từ chối",
                "comment rejected",
                "was rejected",
                "has been rejected",
                "removed",
                "đã bị gỡ",
            ]
            return self.driver.execute_script(
                """
                var post = arguments[0];
                var phrases = arguments[1] || [];
                if (!post) return '';
                var text = (post.innerText || post.textContent || '').toLowerCase();
                for (var i=0;i<phrases.length;i++) {
                    if (text.indexOf(phrases[i]) !== -1) return phrases[i];
                }
                return '';
                """,
                post_el,
                phrases,
            ) or ""
        except Exception:
            return ""

    def _log(self, msg, tag="info"):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.status_var.set(msg)
        self.update_idletasks()

    def _is_action_blocked(self):
        """Detect FB rate-limit / action block dialogs and messages."""
        try:
            return bool(self.driver.execute_script(
                """
                function norm(s){return (s||'').toLowerCase();}
                var bodyText = norm(document.body && (document.body.innerText || document.body.textContent));
                var needles = [
                    // EN
                    "you can't do this right now",
                    "temporarily blocked",
                    "try again later",
                    "we limit how often",
                    // VI
                    "giờ bạn chưa dùng được tính năng này",
                    "để bảo vệ cộng đồng khỏi spam",
                    "chúng tôi giới hạn tần suất",
                    "bạn hiện không thể",
                    "hãy thử lại sau",
                    "tạm thời bị chặn"
                ];
                for (var i=0;i<needles.length;i++) {
                    if (bodyText && bodyText.indexOf(needles[i]) !== -1) return true;
                }

                // Also detect visible dialog headings
                var dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
                for (var j=0;j<dialogs.length;j++) {
                    try {
                        var t = norm(dialogs[j].innerText || dialogs[j].textContent);
                        if (!t) continue;
                        if (t.indexOf('giờ bạn chưa dùng được tính năng này') !== -1) return true;
                        if (t.indexOf("you can't do this right now") !== -1) return true;
                        if (t.indexOf('try again later') !== -1) return true;
                    } catch(e) {}
                }
                return false;
                """
            ))
        except Exception:
            return False

    def _check_page_state(self):
        """Debug: Kiểm tra trạng thái trang - [dir=auto], dialogs, scroll..."""
        try:
            import os
            state = self.driver.execute_script("""
                return {
                    dirAutos: document.querySelectorAll('[dir="auto"]').length,
                    visibleDirAutos: Array.from(document.querySelectorAll('[dir="auto"]')).filter(el => {
                        var style = window.getComputedStyle(el);
                        return style.display !== 'none' && el.offsetHeight > 0;
                    }).length,
                    dialogs: document.querySelectorAll('[role="dialog"]').length,
                    visibleDialogs: Array.from(document.querySelectorAll('[role="dialog"]')).filter(d => {
                        var style = window.getComputedStyle(d);
                        return style.display !== 'none' && d.offsetHeight > 0;
                    }).length,
                    scrollHeight: document.documentElement.scrollHeight,
                    scrollTop: window.scrollY,
                    windowHeight: window.innerHeight,
                    // Sample first [dir="auto"] text
                    sampleText: document.querySelector('[dir="auto"]')?.textContent?.substring(0, 50) || 'none'
                };
            """)
            self._log(f"  [PAGE_STATE] dirAutos={state['dirAutos']} (visible={state['visibleDirAutos']}), " +
                     f"dialogs={state['dialogs']} (visible={state['visibleDialogs']}), " +
                     f"scroll={state['scrollTop']}/{state['scrollHeight']}, " +
                     f"sample='{state['sampleText']}'", "debug")
        except Exception as e:
            self._log(f"  [dbg] Lỗi check page_state: {e}", "debug")
    
    def _close_all_dialogs(self, aggressive=False):
        """Đóng tất cả dialog/modal trên trang."""
        try:
            # Escape keys
            from selenium.webdriver.common.action_chains import ActionChains
            esc_count = 10 if aggressive else 5
            for _ in range(esc_count):
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.1)
            
            # JS: Click close buttons (actual close, not just hide)
            js_close = """
            var removed = 0;
            var dialogs = document.querySelectorAll('[role="dialog"]');
            for (var i = dialogs.length - 1; i >= 0; i--) {
                var d = dialogs[i];

                // Prefer clicking explicit confirmation buttons (e.g., rate-limit popup "OK")
                try {
                    var btns = d.querySelectorAll('button');
                    for (var b = 0; b < btns.length; b++) {
                        var t = (btns[b].innerText || btns[b].textContent || '').trim().toLowerCase();
                        if (t === 'ok' || t === 'đồng ý' || t === 'okay' || t === 'lúc khác' || t === 'not now' || t === 'bỏ qua' || t === 'skip' || t === 'để sau') {
                            btns[b].click();
                            removed++;
                            // move to next dialog
                            d = null;
                            break;
                        }
                    }
                    if (d === null) continue;
                } catch(e) {}

                // Try multiple close button selectors
                var x_btn = d.querySelector('button[aria-label*="Close"]') ||
                            d.querySelector('button[aria-label*="Đóng"]') ||
                            d.querySelector('[data-testid="modal_header_close"]') ||
                            d.querySelector('svg[aria-label*="Close"]')?.closest('button') ||
                            d.querySelector('svg[aria-label*="Đóng"]')?.closest('button');
                
                if (x_btn) {
                    try { 
                        x_btn.click(); 
                        removed++;
                    } catch(e) {}
                } else {
                    // Fallback: remove from DOM if no close button found
                    try {
                        d.parentElement.removeChild(d);
                        removed++;
                    } catch(e) {}
                }
            }
            
            // Hide overlays/backdrops
            var overlays = document.querySelectorAll('div[style*="position"]');
            for (var j = 0; j < overlays.length; j++) {
                var style = window.getComputedStyle(overlays[j]);
                if (style.position === 'fixed' && style.zIndex > 1000) {
                    try {
                        overlays[j].parentElement.removeChild(overlays[j]);
                        removed++;
                    } catch(e) {}
                }
            }
            
            return removed;
            """
            count = self.driver.execute_script(js_close) or 0
            return count
        except Exception as e:
            self._log(f"  [warn] Lỗi khi đóng dialog: {e}", "warning")
            return 0

    def _set_login_ui(self, logged: bool):
        self.logged_in = logged
        if logged:
            self.lbl_login_status.configure(text="●  Đã đăng nhập", fg=GREEN)
            self.btn_login.configure(state="disabled")
            try:
                self.after(200, self._restore_comment_groups_cache)
                self.after(250, self._restore_approval_groups_cache)
            except Exception:
                pass
        else:
            self.lbl_login_status.configure(text="●  Chưa đăng nhập", fg=FG_MUTED)
            self.btn_login.configure(state="normal", text="🌐  Mở Chrome & Đăng nhập")

    # ══════════════════════════════════════════════════════════════════════════
    # Selenium – Đăng nhập
    # ══════════════════════════════════════════════════════════════════════════
    def _init_driver(self):
        if self.driver:
            return
        import os, shutil

        self._log("🔄  Đang khởi động Chrome...", "info")

        # Profile Chrome thật (để copy cookie lần ĐẦU)
        real_profile = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google", "Chrome", "User Data", "Default"
        )

        # Profile riêng của app (lưu phiên đăng nhập cho các lần sau)
        profile_suffix = f"_{self.profile_name}" if self.profile_name != "default" else ""
        app_profile = os.path.join(os.path.dirname(__file__), f"fb_chrome_profile{profile_suffix}")
        app_default = os.path.join(app_profile, "Default")
        os.makedirs(app_default, exist_ok=True)

        # Chỉ copy cookie từ Chrome thật MỘT LẦN duy nhất (chỉ áp dụng cho profile default)
        marker = os.path.join(app_profile, ".cookies_copied")
        should_clone_cookies = (self.profile_name == "default")

        if should_clone_cookies and not os.path.isfile(marker) and os.path.isdir(real_profile):
            self._log("📋  Lần đầu tiên: sao chép cookie từ Chrome thật của bạn...", "info")
            cookie_files = [
                "Cookies", "Cookies-journal",
                "Network\\Cookies", "Network\\Cookies-journal",
                "Login Data", "Login Data-journal",
                "Web Data", "Web Data-journal",
                "Preferences", "Secure Preferences",
            ]

            copied = 0
            for fname in cookie_files:
                src = os.path.join(real_profile, fname)
                dst = os.path.join(app_default, fname)

                # Tạo thư mục cha nếu cần (cho Network\Cookies)
                os.makedirs(os.path.dirname(dst), exist_ok=True)

                if os.path.isfile(src):
                    try:
                        shutil.copy2(src, dst)
                        copied += 1
                    except Exception:
                        # Bỏ qua file đang bị lock
                        pass

            # Copy Local Storage (nếu được)
            ls_src = os.path.join(real_profile, "Local Storage")
            ls_dst = os.path.join(app_default, "Local Storage")
            if os.path.isdir(ls_src):
                try:
                    if os.path.isdir(ls_dst):
                        shutil.rmtree(ls_dst, ignore_errors=True)
                    shutil.copytree(ls_src, ls_dst)
                    copied += 1
                except Exception:
                    pass

            if copied > 0:
                # Đánh dấu đã copy để LẦN SAU KHÔNG GHI ĐÈ cookie bạn đã đăng nhập
                try:
                    with open(marker, "w", encoding="utf-8") as f:
                        f.write("cloned")
                except Exception:
                    pass
                self._log(f"✅  Đã sao chép {copied} file/thư mục cookie (chỉ làm 1 lần).", "ok")
            else:
                self._log("⚠  Không thể sao chép cookie (có thể Chrome đang mở). Bạn hãy đăng nhập thủ công.", "warn")

        elif not os.path.isfile(marker) and self.profile_name != "default":
            # Với profile phụ: KHÔNG clone cookie để tránh dùng chung tài khoản
            self._log(
                f"ℹ  Profile '{self.profile_name}' mới – hãy đăng nhập Facebook cho profile này trong cửa sổ Chrome.",
                "info",
            )
            try:
                with open(marker, "w", encoding="utf-8") as f:
                    f.write("fresh")
            except Exception:
                pass

        elif os.path.isfile(marker):
            if self.profile_name == "default":
                self._log("ℹ  Cookie đã được sao chép trước đó – giữ nguyên phiên đăng nhập hiện tại.", "info")
            else:
                self._log("ℹ  Profile đã khởi tạo – giữ nguyên phiên đăng nhập hiện tại.", "info")

        else:
            # default profile but can't find real profile to clone from
            self._log("⚠  Không tìm thấy Chrome profile thật để sao chép cookie.", "warn")

        opts = webdriver.ChromeOptions()
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--lang=vi")
        opts.add_argument(f"--user-data-dir={app_profile}")
        opts.add_argument("--enable-logging")
        opts.add_argument("--v=1")
        
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        opts.add_experimental_option("prefs", prefs)
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=opts
        )
        
        # Enable browser logs
        try:
            self.driver.execute_cdp_cmd('Console.enable', {})
        except Exception:
            pass
        
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
        )
        self._log("✅  Chrome đã khởi động.", "info")

    def _do_login(self):
        """Mở Chrome  facebook.com. Nếu đã đăng nhập sẵn thì tự động xác nhận.
        Nếu chưa, người dùng tự đăng nhập rồi nhấn Xác nhận."""
        self.btn_login.configure(state="disabled", text="Đang mở Chrome...")
        threading.Thread(target=self._open_browser_thread, daemon=True).start()

    def _is_logged_in(self) -> bool:
        """Kiểm tra đã đăng nhập Facebook chưa dựa vào URL hiện tại."""
        try:
            url = self.driver.current_url
            # Nếu URL không chứa 'login' và đang ở facebook.com thì đã đăng nhập
            return ("facebook.com" in url
                    and "login" not in url
                    and "checkpoint" not in url
                    and "recover" not in url)
        except Exception:
            return False

    def _open_browser_thread(self):
        try:
            self._init_driver()

            def _is_service_unavailable():
                try:
                    txt = self.driver.execute_script(
                        "return (document.body && (document.body.innerText || document.body.textContent) || '').toLowerCase();"
                    ) or ""
                    return ("service unavailable" in txt
                            or "dịch vụ hiện không khả dụng" in txt
                            or "tạm thời không truy cập" in txt)
                except Exception:
                    return False
            
            # Đơn giản: navigate trực tiếp, chờ trang load xong
            self._log("🌐  Đang điều hướng đến facebook.com...", "info")
            self.driver.get("https://www.facebook.com/")
            
            # Chờ page load xong (10 giây)
            self._log("⏳  Chờ trang Facebook tải...", "info")
            time.sleep(5)
            
            # Kiểm tra URL hiện tại
            current = self.driver.current_url
            self._log(f"📍  URL hiện tại: {current}", "info")

            # Nếu gặp Service Unavailable trong profile Selenium, thử làm sạch cookie rồi vào lại
            if _is_service_unavailable():
                self._log("⚠  Facebook báo Service Unavailable trong phiên Chrome tự động. Thử làm sạch cookie...", "warn")
                try:
                    self.driver.delete_all_cookies()
                except Exception:
                    pass
                time.sleep(1)
                self.driver.get("https://m.facebook.com/")
                time.sleep(4)
                if _is_service_unavailable():
                    self._log("⚠  Vẫn lỗi Service Unavailable. Thử lại facebook.com...", "warn")
                    self.driver.get("https://www.facebook.com/?_rdr")
                    time.sleep(4)
                current = self.driver.current_url
                self._log(f"📍  URL sau khi thử lại: {current}", "info")
            
            # Nếu không phải Facebook, thử lại
            if "facebook.com" not in current.lower():
                self._log("⚠  Chưa vào được Facebook, thử lần 2...", "warn")
                self.driver.get("https://www.facebook.com/")
                time.sleep(5)
                current = self.driver.current_url
                self._log(f"📍  URL sau lần 2: {current}", "info")
            
            # Kiểm tra đăng nhập
            if "facebook.com" in current.lower():
                time.sleep(2)
                if self._is_logged_in():
                    self._log("✅  Đã đăng nhập sẵn! Xác nhận thành công.", "ok")
                    self._set_login_ui(True)
                else:
                    self._log("🔐  Chrome đã mở Facebook. Hãy đăng nhập xong rồi chạy lại app.", "warn")
                    self.btn_login.configure(state="normal", text="🌐  Mở Chrome & Đăng nhập")
            else:
                if _is_service_unavailable():
                    self._log("❌  Facebook báo Service Unavailable trong profile tự động.", "err")
                    self._log("👉  Gợi ý: xoá thư mục fb_chrome_profile để tạo profile mới, rồi đăng nhập lại.", "warn")
                else:
                    self._log(f"❌  Không thể mở Facebook. URL hiện tại: {current}", "err")
                self.btn_login.configure(state="normal", text="🌐  Mở Chrome & Đăng nhập")

        except Exception as e:
            self._log(f"❌  Lỗi: {e}", "err")
            import traceback
            self._log(traceback.format_exc(), "err")
            self.btn_login.configure(state="normal", text="🌐  Mở Chrome & Đăng nhập")

    def _do_confirm(self):
        """Người dùng nhấn xác nhận sau khi đã đăng nhập trong Chrome."""
        threading.Thread(target=self._confirm_thread, daemon=True).start()

    def _confirm_thread(self):
        try:
            if not self.driver:
                self._log("❌  Chưa mở Chrome. Hãy nhấn «Mở Chrome & Đăng nhập» trước.", "err")
                return
            self._log("🔍  Kiểm tra trạng thái đăng nhập...", "info")
            time.sleep(1)
            if self._is_logged_in():
                self._log("✅  Xác nhận thành công! Đã đăng nhập Facebook.", "ok")
                self._set_login_ui(True)
            else:
                self._log(f"⚠  Chưa đăng nhập xong. URL hiện tại: {self.driver.current_url}\n"
                          "Hãy hoàn tất đăng nhập trong Chrome rồi nhấn Xác nhận lại.", "err")
        except Exception as e:
            self._log(f"❌  Lỗi xác nhận: {e}", "err")

    def _do_logout(self):
        if self.driver:
            try: self.driver.quit()
            except Exception: pass
            self.driver = None
        self._set_login_ui(False)
        self.posts = []
        self.progress["value"] = 0
        self._log("🚪  Đã đăng xuất và đóng trình duyệt.", "warn")

    # ══════════════════════════════════════════════════════════════════════════
    # Selenium – helper tìm phần tử theo nhiều XPath
    # ══════════════════════════════════════════════════════════════════════════
    def _find_first_xpath(self, root, xpaths, wait_seconds: float = 0):
        """Thử lần lượt danh sách XPath và trả về phần tử đầu tiên tìm được.
        Nếu wait_seconds > 0 sẽ dùng WebDriverWait trên từng XPath.
        """
        last_err = None
        for xp in xpaths:
            try:
                if wait_seconds > 0:
                    el = WebDriverWait(self.driver, wait_seconds).until(
                        EC.presence_of_element_located((By.XPATH, xp))
                    )
                else:
                    el = root.find_element(By.XPATH, xp)
                return el
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err if last_err is not None else Exception("Không tìm thấy phần tử với bất kỳ XPath nào")

    # ══════════════════════════════════════════════════════════════════════════
    # Selenium – Quét & Sửa tự động (gộp fetch + fix)
    # ══════════════════════════════════════════════════════════════════════════
    def _do_auto_fix(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập trước!")
            return
        self._stop_flag = False
        threading.Thread(target=self._auto_fix_thread, daemon=True).start()

    def _auto_fix_thread(self):
        """Gộp fetch + fix: tìm bài  sửa luôn từng bài ngay khi tìm thấy."""
        # Đọc quy tắc từ UI
        rules = self._get_rules_from_ui()
        if not rules:
            self._log("⚠  Không có quy tắc nào được nhập. Vui lòng nhập quy tắc trước.", "err")
            return
        
        # DEBUG: Hiện keywords được tìm
        self._log(f"  [dbg] Keywords để tìm: {[p.pattern for p, _ in rules]}", "info")
        
        try:
            # Nếu checkbox "Quét đến hết trang" bật → limit = 999999, max_scroll = 9999
            scan_all = self.var_scan_all.get()
            if scan_all:
                limit = 999999
                self._log("📥  Mode: Quét đến hết trang...", "info")
            else:
                limit = int(self.spin_count.get())
                self._log(f"📥  Mode: Quét {limit} bài...", "info")
            
            self._log("📥  Mở trang cá nhân...", "info")
            self.driver.get("https://www.facebook.com/me")
            time.sleep(4)
            profile_url = self.driver.current_url.split("?")[0].rstrip("/")
            self._log(f"🔗  {profile_url}", "info")

            # Quay về trang gốc
            self._log(f"📋  Mở trang: {profile_url}", "info")
            self.driver.get(profile_url)
            time.sleep(8)  # Chờ lâu hơn để trang load hết bài

            # ── Đóng tất cả dialog cũ trước khi quét (AGGRESSIVE) ──
            self._log("  [dbg] Đang đóng tất cả dialog cũ (AGGRESSIVE)...", "info")
            try:
                # Cách 1: Thử Escape 10 lần
                for _close_try in range(10):
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.2)
                
                time.sleep(0.5)
                
                # Cách 2: Tìm và click tất cả nút close/X trong dialog
                js_close = """
                var removed = 0;
                // Tìm tất cả [role="dialog"]
                var dialogs = document.querySelectorAll('[role="dialog"]');
                console.log('[JS_CLOSE] Tìm thấy ' + dialogs.length + ' dialog');
                
                for (var i = 0; i < dialogs.length; i++) {
                    var d = dialogs[i];
                    // Thử nhiều selector cho nút close
                    var x_btn = d.querySelector('button[aria-label*="Close"]') ||
                                d.querySelector('button[aria-label*="Đóng"]') ||
                                d.querySelector('button[aria-label*="close"]') ||
                                d.querySelector('[data-testid="modal_header_close"]') ||
                                d.querySelector('button:first-of-type') ||
                                d.querySelector('svg[aria-label*="Close"]')?.parentElement ||
                                d.querySelector('svg[aria-label*="Đóng"]')?.parentElement;
                    
                    if (x_btn) {
                        try {
                            x_btn.click();
                            removed++;
                            console.log('[JS_CLOSE] Clicked close button');
                        } catch (e) {
                            console.log('[JS_CLOSE] Failed to click: ' + e.message);
                        }
                    }
                    
                    // Fallback: hide dialog với CSS
                    try {
                        d.style.display = 'none';
                        removed++;
                        console.log('[JS_CLOSE] Hid dialog with CSS');
                    } catch (e) {}
                }
                
                // Tìm overlay và ẩn
                var overlays = document.querySelectorAll('div[style*="position"]');
                for (var j = 0; j < overlays.length; j++) {
                    var style = window.getComputedStyle(overlays[j]);
                    if (style.position === 'fixed' && style.zIndex > 100) {
                        overlays[j].style.display = 'none';
                    }
                }
                
                return removed;
                """
                closed_count = self.driver.execute_script(js_close) or 0
                self._log(f"  [dbg] Đóng/Ẩn {closed_count} dialog bằng click+CSS.", "info")
                time.sleep(0.5)
                
                self._log("  [dbg] Dialog đã đóng, sẵn sàng quét.", "info")
            except Exception as e:
                self._log(f"  [err] Lỗi khi đóng dialog: {e}", "warning")
                pass

            processed = []  # [{el, text}, ...] - bài đã xử lý
            seen_ids  = set()
            seen_texts = set()  # Track by content hash instead of element ID
            scroll    = 0
            max_scroll = 9999 if scan_all else 150  # Nếu quét hết trang → 9999
            idle_rounds = 0
            fixed_count = 0
            skipped_count = 0

            js_keywords = [p.pattern for p, _ in rules]
            js_skip = ["Bạn đang nghĩ gì", "What's on your mind", "Ảnh/video", "Photo/video"]
            
            # Thử navigate trực tiếp đến /posts hoặc click tab
            current_url = self.driver.current_url
            if '/posts' not in current_url:
                # Try 1: Navigate to /posts URL directly
                try:
                    posts_url = current_url.rstrip('/') + '/posts'
                    self._log(f"  [dbg] Thử mở URL posts: {posts_url}", "info")
                    self.driver.get(posts_url)
                    time.sleep(5)
                    current_url = self.driver.current_url
                    self._log(f"📋  Đã mở trang posts: {current_url}", "info")
                except Exception as e:
                    self._log(f"  [dbg] Lỗi khi mở /posts URL: {e}", "debug")
                    
                    # Try 2: Click tab
                    tab_clicked = False
                    for tab_text in ["Bài viết", "Posts"]:
                        try:
                            tab = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.XPATH,
                                    f'//a[normalize-space(.)="{tab_text}"] | //div[@role="tab" and normalize-space(.)="{tab_text}"]'
                                ))
                            )
                            self.driver.execute_script("arguments[0].click()", tab)
                            self._log(f"📋  Đã click tab '{tab_text}'.", "info")
                            time.sleep(4)
                            tab_clicked = True
                            break
                        except Exception:
                            pass
                    
                    if not tab_clicked:
                        self._log(f"  [dbg] KHÔNG tìm thấy tab 'Bài viết' - sử dụng trang hiện tại.", "warning")
            
            # Check URL sau khi navigate/click
            current_url = self.driver.current_url
            self._log(f"  [dbg] URL hiện tại: {current_url}", "debug")
            
            # ⚡ PRE-SCROLL: Scroll + wait lâu trước loop để Facebook load tất cả bài
            self._log(f"  [dbg] Pre-scroll: Scroll để load bài từ trang...", "info")
            
            # STEP 1: Scroll to TOP trước
            self.driver.execute_script("window.scrollTo(0, 0)")
            time.sleep(2)
            
            # STEP 2: Cleanup cứng nhắc LOOP 5 lần
            for cleanup_round in range(5):
                cleanup_js = """
                // Xóa tất cả dialogs, modals, overlays, video players
                var remove_selectors = [
                    '[role="dialog"]',
                    '[role="presentation"]',
                    '.modal',
                    '.overlay',
                    '[aria-modal="true"]',
                    '[data-testid*="modal"]',
                    'div[style*="position: fixed"]',
                    'div[style*="z-index"]'
                ];
                
                for (var s = 0; s < remove_selectors.length; s++) {
                    var els = document.querySelectorAll(remove_selectors[s]);
                    for (var i = els.length - 1; i >= 0; i--) {
                        try { 
                            els[i].style.display = 'none';
                            if (els[i].parentElement) els[i].parentElement.removeChild(els[i]); 
                        } catch(e) {}
                    }
                }
                
                // Xóa fixed/absolute overlays
                var all = document.querySelectorAll('*');
                for (var i = all.length - 1; i >= 0; i--) {
                    var el = all[i];
                    try {
                        var style = window.getComputedStyle(el);
                        if ((style.position === 'fixed' || style.position === 'absolute') && 
                            (style.zIndex > 100 || el.offsetHeight > window.innerHeight)) {
                            el.style.display = 'none';
                            if (el.parentElement) el.parentElement.removeChild(el);
                        }
                    } catch(e) {}
                }
                
                return 'cleaned';
                """
                try:
                    self.driver.execute_script(cleanup_js)
                except Exception:
                    pass
                time.sleep(0.5)
            
            # Debug: Kiểm tra sau cleanup còn mấy dialogs
            try:
                remaining_dialogs = self.driver.find_elements(By.XPATH, '//div[@role="dialog"]')
                displayed_dialogs = [d for d in remaining_dialogs if d.is_displayed()]
                self._log(f"  [dbg] Sau cleanup: còn {len(displayed_dialogs)} dialogs.", "debug")
            except Exception:
                pass
            
            # Check page state TRƯỚC scroll bottom
            self._check_page_state()
            
            # STEP 3A: Reset styles có thể chặn feed
            self.driver.execute_script("""
                // Ensure body/html not hidden
                document.documentElement.style.overflow = 'auto';
                document.body.style.overflow = 'auto';
                
                // Find + unhide feed container
                var feed = document.querySelector('[role="main"]') || 
                           document.querySelector('div[style*="overflow"]') ||
                           document.querySelector('.xb57i69');
                if (feed) feed.style.overflow = 'auto';
            """)
            time.sleep(1)
            
            # STEP 3: PRE-SCROLL để load một số posts ban đầu
            if scan_all:
                # Mode "Quét hết trang": Scroll xuống vài lần để load thêm posts
                self._log(f"  [dbg] Scroll xuống vài lần để load posts...", "info")
                for pre_scroll in range(5):
                    self.driver.execute_script("window.scrollBy(0, 1000);")
                    time.sleep(2)
                self._log(f"  [dbg] Hoàn tất pre-scroll. Bắt đầu quét...", "info")
            else:
                # Normal mode: Scroll to bottom once
                self.driver.execute_script("""
                    var scrollHeight = Math.max(
                        document.body.scrollHeight,
                        document.documentElement.scrollHeight,
                        document.body.offsetHeight,
                        document.documentElement.offsetHeight,
                        document.body.clientHeight,
                        document.documentElement.clientHeight
                    );
                    window.scrollTo(0, scrollHeight);
                """)
                time.sleep(5)  # Wait 5s để Facebook load hết bài

            # JS tìm bài - TRY MULTIPLE SELECTORS
            JS_FIND = """
            var keywords    = arguments[0];
            var skipPhrases = arguments[1];

            var regexps = keywords.map(function(k){
                var kn = k.normalize ? k.normalize('NFC') : k;
                return new RegExp(kn, 'i');
            });

            function hasKw(t){
                var tn = t && t.normalize ? t.normalize('NFC') : (t||'');
                for(var i=0;i<regexps.length;i++) if(regexps[i].test(tn)) return true;
                return false;
            }
            
            function hasSkip(t){
                for(var i=0;i<skipPhrases.length;i++) if((t||'').indexOf(skipPhrases[i])!==-1) return true;
                return false;
            }

            var results = [], seenCards = [];
            
            // Try multiple selectors in order
            var textElements = [];
            var selectorUsed = '';
            
            var selectors = [
                { query: '[dir="auto"]', name: '[dir="auto"]' },
                { query: '[role="article"]', name: '[role="article"]' },
                { query: 'article', name: '<article>' },
                { query: 'div[data-testid*="post"]', name: '[data-testid*="post"]' }
            ];
            
            for (var s = 0; s < selectors.length; s++) {
                textElements = document.querySelectorAll(selectors[s].query);
                selectorUsed = selectors[s].name;
                console.log('[JS_FIND] Try ' + selectorUsed + ': ' + textElements.length + ' elements');
                if (textElements.length > 0) break;
            }
            
            console.log('[JS_FIND] Using selector: ' + selectorUsed + ' with ' + textElements.length + ' elements');
            
            // DEBUG: Collect debug info to return to Python
            var debugInfo = {
                selectorUsed: selectorUsed,
                totalElements: textElements.length,
                sampleTexts: [],
                keywordMatches: [],
                skipMatches: [],
                noMenuMatches: []
            };
            
            // Collect first 10 sample texts (to see actual posts, not just header)
            for (var debug_i = 0; debug_i < Math.min(10, textElements.length); debug_i++) {
                var sample = textElements[debug_i].textContent || '';
                debugInfo.sampleTexts.push(sample.substring(0, 120));
            }
            
            var kw_count = 0, skip_count = 0, no_menu = 0;
            
            for(var i=0; i<textElements.length; i++){
                var textEl = textElements[i];
                var text = textEl.textContent || '';
                if(text.length < 5) continue;  // Ignore tiny elements
                
                // Có keyword không?
                if(!hasKw(text)) continue;
                kw_count++;
                
                // DEBUG: Collect matched keyword
                if (kw_count <= 5) {
                    debugInfo.keywordMatches.push(text.substring(0, 80));
                }
                
                // Skip skip-phrases?
                if(hasSkip(text)) { 
                    skip_count++; 
                    if (skip_count <= 3) {
                        debugInfo.skipMatches.push(text.substring(0, 80));
                    }
                    continue; 
                }
                
                // Tìm post container có nút "..." (aria-haspopup="menu")
                var p = textEl;
                var postEl = null;
                var depth = 0;
                
                while(p && depth < 20){
                    if(p.querySelector('[aria-haspopup="menu"]')){
                        postEl = p;
                        break;
                    }
                    p = p.parentElement;
                    depth++;
                }
                
                if(!postEl) { 
                    no_menu++; 
                    if (no_menu <= 3) {
                        debugInfo.noMenuMatches.push(text.substring(0, 80));
                    }
                    continue; 
                }
                
                // Dedup
                var isDupe = false;
                for(var k=0; k<seenCards.length; k++){
                    if(seenCards[k] === postEl) { isDupe = true; break; }
                }
                if(isDupe) continue;
                
                seenCards.push(postEl);
                results.push({el: postEl, text: text});
            }
            
            console.log('[JS_FIND] RESULT: textElements=' + textElements.length + ', kw_match=' + kw_count + ', skip=' + skip_count + ', no_menu=' + no_menu + ', FOUND=' + results.length);
            
            // Return results with debug info
            return {
                posts: results,
                debug: debugInfo,
                stats: {
                    totalElements: textElements.length,
                    kwMatches: kw_count,
                    skipMatches: skip_count,
                    noMenuMatches: no_menu,
                    foundPosts: results.length
                }
            };
            """

            while len(processed) < limit and scroll < max_scroll and not self._stop_flag:
                before_find_count = len(seen_texts)  # Track NEW posts found, not processed

                # Bấm "Xem thêm" (retry 2 lần)
                try:
                    for _see_more_try in range(2):
                        see_more_btns = self.driver.find_elements(
                            By.XPATH,
                            '//*[@role="button" and (contains(.,"Xem thêm") or contains(.,"See more"))]'
                        )
                        if not see_more_btns:
                            break
                        for smb in see_more_btns:
                            try:
                                if smb.is_displayed():
                                    self.driver.execute_script("arguments[0].click()", smb)
                                    time.sleep(0.3)
                            except Exception:
                                pass
                except Exception:
                    pass

                # Tìm bài mới
                try:
                    # Kiểm tra: có dialog nào xuất hiện không? Nếu có thì đóng AGGRESSIVE
                    hidden = self._close_all_dialogs(aggressive=True)
                    if hidden > 0:
                        self._log(f"  [dbg] Ẩn {hidden} dialog xuất hiện.", "warning")
                    time.sleep(2)  # Wait 2s sau close dialogs để DOM render hoàn toàn
                    
                    # AGGRESSIVE cleanup NGAY TRƯỚC JS_FIND (mỗi iteration)
                    try:
                        self.driver.execute_script("""
                            // Remove ALL overlays, modals, video players
                            var toRemove = document.querySelectorAll('[role="dialog"], [aria-modal="true"], [role="presentation"], .modal, .overlay, [data-testid*="modal"]');
                            for (var i = toRemove.length - 1; i >= 0; i--) {
                                try { 
                                    toRemove[i].style.display = 'none';
                                    if (toRemove[i].parentElement) toRemove[i].parentElement.removeChild(toRemove[i]); 
                                } catch(e) {}
                            }
                            return toRemove.length;
                        """)
                    except Exception:
                        pass
                    time.sleep(0.5)
                    
                    # Scroll TRƯỚC lần đầu để Facebook load posts
                    if scroll == 0:
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(5)
                    
                    self._log(f"  [dbg] Chạy JS_FIND lần #{scroll}...", "info")
                    
                    # Log trước JS_FIND: kiểm tra [dir="auto"] count + dialogs
                    try:
                        pre_state = self.driver.execute_script("""
                            return {
                                dirAutos: document.querySelectorAll('[dir="auto"]').length,
                                dialogs: document.querySelectorAll('[role="dialog"]').length,
                                visibleDialogs: Array.from(document.querySelectorAll('[role="dialog"]')).filter(d => {
                                    var style = window.getComputedStyle(d);
                                    return style.display !== 'none' && d.offsetHeight > 0;
                                }).length
                            };
                        """)
                        self._log(f"  [dbg] Trước JS_FIND: {pre_state['dirAutos']} [dir=auto], {pre_state['dialogs']} dialogs ({pre_state['visibleDialogs']} visible)", "debug")
                    except Exception as e:
                        self._log(f"  [dbg] Lỗi check pre-state: {e}", "debug")
                    
                    # Execute JS_FIND and parse result
                    js_result = self.driver.execute_script(JS_FIND, js_keywords, js_skip) or {}
                    found_items = js_result.get('posts', []) if isinstance(js_result, dict) else []
                    
                    # Print debug info
                    if isinstance(js_result, dict) and 'debug' in js_result:
                        debug_info = js_result['debug']
                        stats = js_result.get('stats', {})
                        self._log(f"  [JS_DEBUG] Selector: {debug_info.get('selectorUsed', 'N/A')}, Total elements: {debug_info.get('totalElements', 0)}", "info")
                        self._log(f"  [JS_DEBUG] Stats: kw_matches={stats.get('kwMatches', 0)}, skip={stats.get('skipMatches', 0)}, no_menu={stats.get('noMenuMatches', 0)}, FOUND={stats.get('foundPosts', 0)}", "info")
                        
                        # Print sample texts
                        if debug_info.get('sampleTexts'):
                            self._log(f"  [JS_DEBUG] First {len(debug_info['sampleTexts'])} sample texts:", "info")
                            for i, sample in enumerate(debug_info['sampleTexts']):
                                self._log(f"    [{i}] {sample}", "info")
                        
                        # Print keyword matches
                        if debug_info.get('keywordMatches'):
                            self._log(f"  [JS_DEBUG] Keyword matches (first {len(debug_info['keywordMatches'])}):", "info")
                            for match in debug_info['keywordMatches']:
                                self._log(f"    - {match}", "info")
                        
                        # Print skip matches
                        if debug_info.get('skipMatches'):
                            self._log(f"  [JS_DEBUG] Skipped due to skip-phrases:", "info")
                            for match in debug_info['skipMatches']:
                                self._log(f"    - {match}", "info")
                        
                        # Print no-menu matches
                        if debug_info.get('noMenuMatches'):
                            self._log(f"  [JS_DEBUG] No menu button found:", "info")
                            for match in debug_info['noMenuMatches']:
                                self._log(f"    - {match}", "info")
                    
                    self._log(f"  [dbg] JS_FIND trả về: {len(found_items)} bài", "info")
                    
                    # Nếu 0 bài, aggressive retry: cleanup+scroll+retry JS_FIND
                    if not found_items and scroll < 3:
                        self._log(f"  [dbg] 0 bài ở lần #{scroll}, aggressive retry...", "warning")
                        
                        # Cleanup 3x aggressive
                        for retry_cleanup in range(3):
                            try:
                                self.driver.execute_script("""
                                    // Nuclear option: remove tất cả dialogs + overlays
                                    document.querySelectorAll('[role="dialog"], [aria-modal], [role="presentation"]').forEach(el => {
                                        try { el.parentElement.removeChild(el); } catch(e) {}
                                    });
                                    // Remove all fixed positioned elements on top of feed
                                    Array.from(document.querySelectorAll('*')).filter(el => {
                                        var style = window.getComputedStyle(el);
                                        return style.position === 'fixed' && style.zIndex > 50;
                                    }).forEach(el => {
                                        try { el.parentElement.removeChild(el); } catch(e) {}
                                    });
                                """)
                            except Exception:
                                pass
                            time.sleep(0.3)
                        
                        # Scroll DOWN aggressive (chỉ DOWN, không UP) để load posts mới
                        self.driver.execute_script("window.scrollBy(0, 1500);")
                        time.sleep(2)
                        
                        # Retry JS_FIND
                        js_result = self.driver.execute_script(JS_FIND, js_keywords, js_skip) or {}
                        found_items = js_result.get('posts', []) if isinstance(js_result, dict) else []
                        self._log(f"  [dbg] After retry: JS_FIND trả về {len(found_items)} bài", "info")
                    
                    # Nếu vẫn 0 bài, test alt selectors
                    if not found_items:
                        try:
                            alt_selectors = {
                                '[role="article"]': 'article role',
                                '[data-testid="post"]': 'post testid',
                                '.xdj266r': 'post CSS class (xdj266r)',
                                '[aria-haspopup="menu"]': 'menu aria-haspopup'
                            }
                            for selector, desc in alt_selectors.items():
                                count = self.driver.execute_script(
                                    f"return document.querySelectorAll('{selector}').length;"
                                )
                                self._log(f"  [dbg] {desc} selector = {count} elements", "debug")
                        except Exception as e:
                            self._log(f"  [dbg] Lỗi test alt selectors: {e}", "debug")
                    
                    # Đọc browser console logs (chi tiết debug)
                    try:
                        logs = self.driver.get_log('browser')
                        for log in logs:
                            msg = log.get('message', '')
                            # In TẤT CẢ logs từ console (không chỉ [JS_FIND])
                            if msg.strip():
                                self._log(f"  [js_console] {msg}", "debug")
                    except Exception as e:
                        self._log(f"  [dbg] Lỗi đọc browser logs: {e}", "debug")
                    
                    if found_items:
                        self._log(f"  [dbg] Tìm được {len(found_items)} bài mới ở lần scroll #{scroll}.", "info")
                    else:
                        self._log(f"  [dbg] Không tìm được bài nào ở lần scroll #{scroll}", "warning")
                        # Check lại trang để debug
                        self._check_page_state()
                    
                    for item in found_items:
                        el = item["el"]
                        txt = item["text"]
                        # Use text content hash for deduplication across scrolls
                        txt_hash = hash(txt[:200])  # First 200 chars
                        
                        self._log(f"  [dbg] Bài tìm được: hash={txt_hash}, text_preview={txt[:80]}...", "debug")
                        
                        if txt_hash in seen_texts:
                            self._log(f"  [dbg] → Dedup skip (đã sửa trước).", "debug")
                            continue
                        
                        seen_texts.add(txt_hash)
                        processed.append({"el": el, "text": txt})
                        
                        self._log(f"  [dbg] → Gọi _fix_one_post lần {len(processed)}...", "debug")
                        # Thêm vào queue sửa (bỏ filter, để _fix_one_post check lại khi mở editor)
                        # SỬA LUÔN - hàm sẽ check match lại khi đọc editor text đầy đủ
                        self._fix_one_post({"el": el, "text": txt}, rules, len(processed), limit)
                        
                        if len(processed) % 10 == 0:
                            self._log(f"🔍  Đã xử lý: {len(processed)} bài.", "info")
                        
                        if len(processed) >= limit:
                            break
                except Exception as e:
                    self._log(f"⚠  Lỗi khi quét: {str(e)[:100]}", "warn")

                if len(processed) >= limit:
                    break

                # ⚡ SCROLL STRATEGY: Luôn scroll DOWN (xuống), không scroll UP
                # Mode "Quét hết trang": Scroll chậm hơn để Facebook không unload posts
                if scan_all:
                    # Scroll DOWN 1500px, wait lâu hơn
                    self.driver.execute_script("window.scrollBy(0, 1500);")
                    time.sleep(4)  # Wait 4s cho Facebook load
                else:
                    # Scroll DOWN như cũ
                    self.driver.execute_script("window.scrollBy(0, 1500)")
                    time.sleep(0.5)
                    # Scroll to absolute bottom
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(6)
                
                scroll += 1

                # Check if we found NEW posts (by tracking unique text hashes)
                if len(seen_texts) == before_find_count:
                    # No new unique posts found in this scroll
                    idle_rounds += 1
                    # Nếu "quét hết trang" → chỉ dừng nếu 15 lần không tìm (tức là hết trang)
                    # Nếu bình thường → 8 lần không tìm
                    threshold = 15 if scan_all else 8
                    if idle_rounds >= threshold:
                        self._log(f"ℹ  Đã cuộn {idle_rounds} lần không tìm bài mới, dừng.", "info")
                        break
                else:
                    idle_rounds = 0

            self._log(f"✅  Xong! Đã xử lý {len(processed)} bài.", "ok")
            self.progress["value"] = 100

        except Exception as e:
            self._log(f"❌  Lỗi: {e}", "err")
            import traceback
            self._log(traceback.format_exc(), "err")

    def _fix_one_post(self, post, rules, idx, total):
        """Sửa 1 bài post ngay lập tức."""
        try:
            el = post["el"]
            preview_text, count = apply_rules(post["text"], rules)

            if count == 0:
                self._log(f"  ↷  Bài {idx}: Preview text không match, kiểm tra editor...", "info")
                # Vẫn mở editor để check text đầy đủ
            
            # Kiểm tra element còn hợp lệ
            try:
                _ = el.tag_name
            except Exception:
                self._log(f"  ⚠  Bài {idx}: Element đã stale.", "warn")
                return

            # Cuộn vào giữa màn hình (catch stale element)
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            except Exception as e:
                # Element stale sau khi scroll → skip
                self._log(f"  ⚠  Bài {idx}: Element stale khi scroll: {str(e)[:80]}", "warn")
                return
            time.sleep(1.2)

            # Đóng bất kỳ menu/popup nào đang mở trước khi xử lý bài này
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.4)
            except Exception:
                pass

            # Hover để hiện nút "..." — RETRY 3 lần
            menu_btn = None
            for _hover_try in range(3):
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).move_to_element(el).perform()
                    time.sleep(1.0)
                except Exception:
                    pass

                # Tìm nút "..." - BỎ QUA nút settings/profile
                try:
                    candidates = el.find_elements(
                        By.XPATH,
                        './/*[@aria-haspopup="menu" and (@role="button" or not(@role))]'
                    )
                    for cand in candidates:
                        try:
                            label = cand.get_attribute("aria-label") or ""
                            if any(x in label.lower() for x in ["cài đặt", "settings", "trang cá nhân", "profile", "quản lý trang"]):
                                continue
                            menu_btn = cand
                            break
                        except Exception:
                            pass
                except Exception:
                    pass

                if menu_btn:
                    break
                # Nếu chưa thấy, cuộn lại và thử hover lại
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                except Exception:
                    # Element stale, skip bài này
                    self._log(f"  ⚠  Bài {idx}: Element stale trong lần hover lặp.", "warn")
                    return
                time.sleep(0.5)

            if menu_btn is None:
                self._log(f"  ⚠  Bài {idx}: Không tìm được nút '...'.", "warn")
                return

            # Click nút "..."
            try:
                self.driver.execute_script("arguments[0].click()", menu_btn)
            except Exception:
                try:
                    menu_btn.click()
                except Exception:
                    self._log(f"  ⚠  Bài {idx}: Không click được nút '...'.", "warn")
                    return

            time.sleep(1.5)

            # Đợi popup menu MỚI xuất hiện sau khi click "..."
            # Cách: tìm menu có chứa các item quản lý bài viết (pin, lưu, chỉnh sửa...)
            popup_menu = None
            deadline = time.time() + 12
            while time.time() < deadline:
                try:
                    all_menus = self.driver.find_elements(By.XPATH, '//*[@role="menu"]')
                    for m in reversed(all_menus):  # kiểm tra từ cuối lên
                        try:
                            items_text = m.get_attribute('textContent') or ''
                            # Menu bài viết phải có ít nhất 1 trong các từ sau
                            post_menu_keywords = ['Chỉnh sửa', 'Edit', 'Ghim', 'Pin', 'Xoá', 'Delete',
                                                   'Thùng rác', 'Trash', 'Thông báo', 'Lưu bài', 'Lưu video']
                            if any(kw in items_text for kw in post_menu_keywords):
                                popup_menu = m
                                break
                        except Exception:
                            pass
                    if popup_menu:
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            if popup_menu is None:
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                self._log(f"  ↷  Bài {idx}: Không tìm được menu bài viết.", "info")
                return

            # Debug: xem menu có gì
            try:
                menu_items = popup_menu.find_elements(By.XPATH, './/*[@role="menuitem" or @role="option"]')
                menu_texts = [item.text[:60] for item in menu_items if item.text.strip()]
                self._log(f"  [dbg] Menu popup: {menu_texts}", "info")
            except Exception:
                pass

            # Nhấn "Chỉnh sửa bài viết" - tìm trong popup menu
            edit_item = None
            try:
                # Thử XPath đầu tiên
                edit_item = popup_menu.find_element(
                    By.XPATH,
                    './/*[(@role="menuitem" or @role="option" or @role="button") and '
                    '(contains(.,"Chỉnh sửa bài viết") or contains(.,"Sửa bài viết") or '
                    'contains(.,"Chỉnh sửa bài đăng") or contains(.,"Edit post") or '
                    'contains(.,"Edit Post"))]'
                )
            except Exception:
                # Fallback: tìm bằng JS bất kỳ nút nào trong menu chứa "Chỉnh sửa"
                try:
                    edit_item = self.driver.execute_script("""
                        var menu = arguments[0];
                        var items = menu.querySelectorAll('[role="menuitem"], [role="option"], [role="button"]');
                        for (var i = 0; i < items.length; i++) {
                            var t = (items[i].textContent || '').toLowerCase();
                            if (t.indexOf('chỉnh sửa') !== -1 || t.indexOf('edit') !== -1) {
                                return items[i];
                            }
                        }
                        return null;
                    """, popup_menu)
                except Exception:
                    pass

            if edit_item:
                try:
                    self.driver.execute_script("arguments[0].click()", edit_item)
                except Exception:
                    try:
                        edit_item.click()
                    except Exception:
                        pass
            else:
                # Không tìm được "Chỉnh sửa" → bài người khác
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                self._log(f"  ↷  Bài {idx}: Không tìm được 'Chỉnh sửa bài viết' trong menu.", "info")
                return

            time.sleep(2)

            # Lấy dialog editor
            try:
                dialog = WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, '//div[@role="dialog"]'))
                )
            except Exception:
                self._log(f"  ⚠  Bài {idx}: Không mở được dialog editor.", "warn")
                return

            # Tìm textbox editor — chọn cái có nội dung nhiều nhất
            editor = None
            try:
                # Đợi ít nhất 1 contenteditable xuất hiện
                WebDriverWait(dialog, 8).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        './/div[@contenteditable="true" and @role="textbox"]'
                    ))
                )
                time.sleep(1)
                # Lấy TẤT CẢ contenteditable, chọn cái dài nhất
                all_editors = dialog.find_elements(
                    By.XPATH,
                    './/div[@contenteditable="true" and @role="textbox"]'
                )
                best_len = -1
                for ed in all_editors:
                    try:
                        t = self.driver.execute_script(
                            "return arguments[0].innerText || arguments[0].textContent || '';", ed
                        ) or ""
                        if len(t) > best_len:
                            best_len = len(t)
                            editor = ed
                    except Exception:
                        pass
            except Exception:
                self._log(f"  ⚠  Bài {idx}: Không tìm được textbox editor.", "warn")
                return

            if editor is None:
                self._log(f"  ⚠  Bài {idx}: Editor is None.", "warn")
                return

            # Click vào editor để focus
            self.driver.execute_script("arguments[0].focus(); arguments[0].click();", editor)
            time.sleep(1)

            # ── Đọc nội dung editor (skip nhanh nếu rỗng) ──
            actual_editor_text = ""
            for _retry_read in range(4):  # Giảm từ 8 xuống 4
                actual_editor_text = self.driver.execute_script(
                    "return arguments[0].innerText || arguments[0].textContent || '';",
                    editor
                ) or ""
                if len(actual_editor_text.strip()) > 10:
                    break
                # Thử click lại để kích hoạt render
                self.driver.execute_script("arguments[0].click();", editor)
                time.sleep(0.8)
            
            # Nếu sau retry editor vẫn rỗng → skip ngay (không log, lướt nhanh)
            if len(actual_editor_text.strip()) <= 5:
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.3)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                return

            self._log(f"  [dbg] Editor text ({len(actual_editor_text)} chars): {actual_editor_text[:150]!r}", "info")

            _, actual_count = apply_rules(actual_editor_text, rules)
            if actual_count == 0:
                # Không cần sửa gì → đóng dialog, bỏ qua
                self._log(f"  ↷  Bài {idx}: Không cần sửa (editor không có từ khóa).", "info")
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                self._log(f"  ↷  Bài {idx}: Không cần sửa (editor không có từ khóa).", "info")
                return
            count = actual_count

            # ── Chuẩn bị text mới ──
            new_full_text, _ = apply_rules(actual_editor_text, rules)
            self._log(f"  [dbg] New text preview: {new_full_text[:150]!r}", "info")

            # ══════════════════════════════════════════════════════════════
            # THAY TEXT — Dùng Ctrl+A → clipboard paste (đáng tin cậy nhất)
            # ══════════════════════════════════════════════════════════════
            replace_ok = False

            # ── Phương pháp A: Ctrl+A → Clipboard paste bằng Tkinter ──
            try:
                # 1. Focus editor
                self.driver.execute_script("arguments[0].focus();", editor)
                time.sleep(0.3)

                # 2. Ctrl+A select all
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
                time.sleep(0.5)

                # 3. Copy new text to system clipboard via Tkinter (self is a Tk root)
                self.clipboard_clear()
                self.clipboard_append(new_full_text)
                self.update()
                time.sleep(0.3)

                # 4. Ctrl+V paste
                ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                time.sleep(2)

                # 5. Verify
                check_text = self.driver.execute_script(
                    "return arguments[0].innerText || arguments[0].textContent || '';",
                    editor
                ) or ""
                _, still_count = apply_rules(check_text, rules)
                if still_count == 0 and len(check_text.strip()) > 10:
                    self._log(f"  [dbg] ✓ Ctrl+V paste thành công.", "info")
                    replace_ok = True
                else:
                    self._log(f"  [dbg] Ctrl+V chưa OK (còn {still_count} match, {len(check_text)} chars). Thử cách khác...", "info")
            except Exception as e:
                self._log(f"  [dbg] Ctrl+V lỗi: {e}", "info")

            # ── Phương pháp B: execCommand per-match (Selection API) ──
            if not replace_ok:
                try:
                    # Reset trạng thái: click lại editor, đợi
                    self.driver.execute_script("arguments[0].focus(); arguments[0].click();", editor)
                    time.sleep(1)

                    total_replaced = self.driver.execute_script("""
                        var editor = arguments[0];
                        var rulesJson = arguments[1];
                        editor.focus();
                        var totalReplaced = 0;
                        
                        for (var r = 0; r < rulesJson.length; r++) {
                            var pattern = rulesJson[r][0];
                            var replacement = rulesJson[r][1];
                            var regex = new RegExp(pattern, 'i');
                            
                            var maxIter = 200;
                            while (maxIter-- > 0) {
                                var found = false;
                                var walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT, null, false);
                                while (walker.nextNode()) {
                                    var node = walker.currentNode;
                                    var match = regex.exec(node.textContent);
                                    if (match) {
                                        var range = document.createRange();
                                        range.setStart(node, match.index);
                                        range.setEnd(node, match.index + match[0].length);
                                        
                                        var sel = window.getSelection();
                                        sel.removeAllRanges();
                                        sel.addRange(range);
                                        
                                        document.execCommand('insertText', false, replacement);
                                        totalReplaced++;
                                        found = true;
                                        break;
                                    }
                                }
                                if (!found) break;
                            }
                        }
                        
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                        return totalReplaced;
                    """, editor, [[p.pattern, r] for p, r in rules])

                    self._log(f"  [dbg] execCommand: thay {total_replaced} chỗ.", "info")

                    # Verify
                    check2 = self.driver.execute_script(
                        "return arguments[0].innerText || arguments[0].textContent || '';",
                        editor
                    ) or ""
                    _, still2 = apply_rules(check2, rules)
                    if still2 == 0 and total_replaced > 0:
                        replace_ok = True
                    else:
                        self._log(f"  [dbg] execCommand chưa hoàn toàn (còn {still2} match).", "info")
                except Exception as e:
                    self._log(f"  [dbg] execCommand lỗi: {e}", "info")

            # ── Phương pháp C: selectAll + insertText toàn bộ ──
            if not replace_ok:
                try:
                    self.driver.execute_script("""
                        var editor = arguments[0];
                        var newText = arguments[1];
                        editor.focus();
                        document.execCommand('selectAll');
                        document.execCommand('insertText', false, newText);
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                    """, editor, new_full_text)
                    self._log(f"  [dbg] selectAll+insertText: hoàn tất.", "info")
                    replace_ok = True
                except Exception as e:
                    self._log(f"  ⚠  Bài {idx}: Lỗi thay text (method C): {e}", "warn")

            if not replace_ok:
                self._log(f"  ⚠  Bài {idx}: Không thay được text bằng bất kỳ cách nào.", "warn")
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                return

            time.sleep(1.5)

            # ── Xác nhận lần cuối ──
            try:
                final_text = self.driver.execute_script(
                    "return arguments[0].innerText || arguments[0].textContent || '';",
                    editor
                ) or ""
                _, final_remaining = apply_rules(final_text, rules)
                self._log(f"  [dbg] Sau thay: {final_text[:120]!r} (còn {final_remaining} match)", "info")
            except Exception:
                pass

            # ══════════════════════════════════════════════════════════════
            # Bước SAVE: Click "Tiếp" rồi "Lưu"
            # ══════════════════════════════════════════════════════════════

            # Hàm helper: tìm nút theo text (chính xác)
            JS_FIND_BTN = """
                var labels = arguments[0];
                var btns = document.querySelectorAll('[role="button"], button');
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].textContent || '').trim();
                    for (var j = 0; j < labels.length; j++) {
                        if (t === labels[j]) {
                            // Scroll vào view
                            btns[i].scrollIntoView({block:'center'});
                            return btns[i];
                        }
                    }
                }
                return null;
            """

            # Bước 1: Click "Tiếp" (có thể không có → bỏ qua)
            try:
                tiep_btn = self.driver.execute_script(JS_FIND_BTN, ['Tiếp', 'Next', 'Continue'])
                if tiep_btn:
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click()", tiep_btn)
                    self._log(f"  ▶  Bài {idx}: Đã click 'Tiếp'.", "info")
                    time.sleep(3)
                else:
                    self._log(f"  [dbg] Bài {idx}: Không thấy nút 'Tiếp', thử tìm 'Lưu' trực tiếp.", "info")
            except Exception as e:
                self._log(f"  [dbg] Bài {idx}: Lỗi click Tiếp: {e}", "info")

            # Bước 2: Click "Lưu" (đợi xuất hiện, retry)
            save_btn = None
            for _save_try in range(6):
                try:
                    save_btn = self.driver.execute_script(JS_FIND_BTN,
                        ['Lưu', 'Save', 'Đăng', 'Post', 'Done', 'Submit', 'Cập nhật', 'Update'])
                    if save_btn:
                        self._log(f"  [dbg] Tìm thấy nút 'Lưu' lần {_save_try + 1}.", "info")
                        break
                except Exception as e:
                    self._log(f"  [dbg] Lần {_save_try + 1} tìm 'Lưu' thất bại: {str(e)[:60]}", "info")
                time.sleep(0.8)

            if not save_btn:
                self._log(f"  ⚠  Bài {idx}: Không tìm được nút 'Lưu' sau 6 lần thử, hủy.", "warn")
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                return

            if save_btn:
                try:
                    time.sleep(0.3)
                    self.driver.execute_script("arguments[0].click()", save_btn)
                except Exception:
                    try:
                        save_btn.click()
                    except Exception:
                        pass
                time.sleep(2)  # Wait for save to complete

                # ── Xử lý popup "Thêm nút WhatsApp" nếu có ──
                try:
                    later_btn = self.driver.execute_script("""
                        var labels = ['Lúc khác', 'Later', 'Not now', 'Skip'];
                        var btns = document.querySelectorAll('[role="button"], button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].textContent || '').trim();
                            for (var j = 0; j < labels.length; j++) {
                                if (t === labels[j]) return btns[i];
                            }
                        }
                        return null;
                    """)
                    if later_btn:
                        self.driver.execute_script("arguments[0].click()", later_btn)
                        self._log(f"  [dbg] Đã click 'Lúc khác' để đóng popup WhatsApp.", "info")
                        time.sleep(0.8)
                except Exception:
                    pass

                # Kiểm tra dialog đã đóng chưa (aggressive close)
                dialog_gone = False
                for _check_try in range(6):
                    try:
                        dialogs = self.driver.find_elements(By.XPATH, '//div[@role="dialog"]')
                        displayed_dialogs = [d for d in dialogs if d.is_displayed()]
                        if not displayed_dialogs:
                            dialog_gone = True
                            self._log(f"  [dbg] Dialog đóng lần {_check_try + 1}.", "info")
                            break
                    except Exception:
                        dialog_gone = True
                        break
                    time.sleep(0.5)

                if dialog_gone:
                    self._log(f"  ✅  Đã sửa bài {idx}/{total} ({count} thay thế).", "ok")
                else:
                    # Dialog còn mở → thử close X button
                    self._log(f"  [dbg] Dialog vẫn mở, thử tìm nút X để đóng...", "info")
                    try:
                        close_x = self.driver.execute_script("""
                            var dialogs = document.querySelectorAll('div[role="dialog"]');
                            for (var i = dialogs.length - 1; i >= 0; i--) {
                                if (dialogs[i].style.display !== 'none') {
                                    var x_btn = dialogs[i].querySelector('[aria-label*="Close"], [aria-label*="Đóng"], button[aria-label]');
                                    if (x_btn) return x_btn;
                                }
                            }
                            return null;
                        """)
                        if close_x:
                            self.driver.execute_script("arguments[0].click()", close_x)
                            self._log(f"  [dbg] Đã click nút X đóng dialog.", "info")
                            time.sleep(1)
                        else:
                            # Thử Escape
                            from selenium.webdriver.common.action_chains import ActionChains
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(0.5)
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            self._log(f"  [dbg] Đã nhấn Escape để đóng dialog.", "info")
                    except Exception as e:
                        self._log(f"  ⚠  Bài {idx}: Lỗi đóng dialog: {str(e)[:80]}", "warn")
                    
                    # Final check
                    try:
                        dialogs = self.driver.find_elements(By.XPATH, '//div[@role="dialog"]')
                        displayed = [d for d in dialogs if d.is_displayed()]
                        if displayed:
                            self._log(f"  ⚠  Bài {idx}: Dialog vẫn mở dù đã thử đóng.", "warn")
                        else:
                            self._log(f"  ✅  Đã sửa bài {idx}/{total} ({count} thay thế).", "ok")
                    except Exception:
                        self._log(f"  ✅  Đã sửa bài {idx}/{total} ({count} thay thế).", "ok")
            else:
                self._log(f"  ⚠  Bài {idx}: Không tìm thấy nút 'Lưu', hủy.", "warn")
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass

        except Exception as e:
            self._log(f"  ❌  Bài {idx}: Lỗi không mong muốn: {e}", "err")
            import traceback
            self._log(f"  {traceback.format_exc()}", "err")
        
        # ⚡ CLEANUP: Đóng TẤT CẢ dialog sau sửa để chuẩn bị cho lần quét tiếp theo
        try:
            self._log(f"  [dbg] Cleanup: Đóng dialog sau sửa bài {idx}...", "debug")
            # Retry cleanup nếu vẫn còn nhiều dialogs
            for cleanup_retry in range(3):
                hidden = self._close_all_dialogs(aggressive=True)
                time.sleep(1.5)  # Wait để dialogs hoàn toàn biến mất
                
                # Kiểm tra còn bao nhiêu dialogs
                try:
                    dialogs = self.driver.find_elements(By.XPATH, '//div[@role="dialog"]')
                    displayed = [d for d in dialogs if d.is_displayed()]
                    if len(displayed) <= 2:  # Nếu ≤2 dialogs → OK
                        break
                except Exception:
                    break
        except Exception:
            pass
        
        # Note: Không scroll ở đây nữa, để main loop quản lý scroll strategy

    # ══════════════════════════════════════════════════════════════════════════
    # (Giữ lại _do_fetch và _do_fix_all cho tương thích - nếu cần)
    # ══════════════════════════════════════════════════════════════════════════
    def _do_fetch(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập trước!")
            return
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        # Đọc quy tắc từ UI
        rules = self._get_rules_from_ui()
        if not rules:
            self._log("⚠  Không có quy tắc nào được nhập. Vui lòng nhập quy tắc trước khi tải bài.", "err")
            return
        
        try:
            limit = int(self.spin_count.get())
            self._log("📥  Mở trang cá nhân...", "info")
            self.driver.get("https://www.facebook.com/me")
            time.sleep(4)
            profile_url = self.driver.current_url.split("?")[0].rstrip("/")
            self._log(f"🔗  {profile_url}", "info")

            # Quay về trang gốc (không thêm /posts hay ?sk=2)
            self._log(f"📋  Mở trang: {profile_url}", "info")
            self.driver.get(profile_url)
            time.sleep(5)

            # Thử click tab "Bài viết" / "Posts" trong nav bar của trang
            for tab_text in ["Bài viết", "Posts"]:
                try:
                    tab = WebDriverWait(self.driver, 6).until(
                        EC.element_to_be_clickable((By.XPATH,
                            f'//a[normalize-space(.)="{tab_text}"] | //div[@role="tab" and normalize-space(.)="{tab_text}"]'
                        ))
                    )
                    self.driver.execute_script("arguments[0].click()", tab)
                    self._log(f"📋  Đã click tab '{tab_text}'.", "info")
                    time.sleep(4)
                    break
                except Exception:
                    pass

            self.posts = []
            seen_ids   = set()
            scroll     = 0
            max_scroll = min(limit * 4, 60)
            idle_rounds = 0

            # Thử click tab "Bài viết" / "Posts" nếu trang không tự chuyển
            try:
                posts_tab = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                        '//a[@role="tab" and (contains(.,"Bài viết") or contains(.,"Posts"))]'
                        ' | //div[@role="tab" and (contains(.,"Bài viết") or contains(.,"Posts"))]'
                    ))
                )
                self.driver.execute_script("arguments[0].click()", posts_tab)
                self._log("📋  Đã chuyển sang tab Bài viết.", "info")
                time.sleep(3)
            except Exception:
                pass

            # Chuẩn bị từ khoá dưới dạng chuỗi regex (JS sẽ dùng)
            js_keywords   = [p.pattern for p, _ in rules]
            js_skip       = ["Bạn đang nghĩ gì", "What's on your mind",
                             "Ảnh/video", "Photo/video"]

            # JS tìm bài: dùng [dir="auto"] để xác định bài có từ khoá (tránh nhiễm từ nav),
            # nhưng trả về POST CARD (tổ tiên role=article hoặc container có nút "...")
            # để phần sửa có thể hover và tìm nút đúng.
            JS_FIND = """
            var keywords    = arguments[0];
            var skipPhrases = arguments[1];

            var regexps = keywords.map(function(k){
                var kn = k.normalize ? k.normalize('NFC') : k;
                return new RegExp(kn, 'i');
            });

            var results = [], seenCards = [];
            function inSeen(e){ for(var i=0;i<seenCards.length;i++) if(seenCards[i]===e) return true; return false; }

            function hasKw(t){
                var tn = t && t.normalize ? t.normalize('NFC') : (t||'');
                for(var i=0;i<regexps.length;i++) if(regexps[i].test(tn)) return true;
                return false;
            }
            function hasSkip(t){
                for(var i=0;i<skipPhrases.length;i++) if((t||'').indexOf(skipPhrases[i])!==-1) return true;
                return false;
            }

            var dirAutos = document.querySelectorAll('[dir="auto"]');
            for(var i=0; i<dirAutos.length; i++){
                var contentEl = dirAutos[i];
                var contentText = contentEl.textContent||'';
                if(!hasKw(contentText)) continue;
                if(hasSkip(contentText)) continue;
                // Bỏ qua nếu có con cũng chứa từ khoá (chỉ lấy phần tử nhỏ nhất chứa từ khoá)
                var childHas = false;
                for(var j=0; j<contentEl.children.length; j++){
                    if(hasKw(contentEl.children[j].textContent||'')){ childHas=true; break; }
                }
                if(childHas) continue;

                // Tìm post card = tổ tiên role='article' NGOÀI CÙNG (outermost),
                // vì comment cũng có role='article' nhưng lồng bên trong post article.
                // Nếu không tìm được article nào thì lấy container nhỏ nhất có nút "..."
                var postCard = null;
                var p = contentEl.parentElement;
                while(p && p !== document.body){
                    if(p.getAttribute('role') === 'article'){
                        postCard = p; // KHÔNG break - tiếp tục để lấy outermost
                    }
                    p = p.parentElement;
                }
                if(!postCard){
                    p = contentEl.parentElement;
                    while(p && p !== document.body){
                        if((p.textContent||'').length > 15000) break;
                        if(p.querySelector('[aria-haspopup="menu"]')){
                            postCard = p;
                        }
                        p = p.parentElement;
                    }
                }
                if(!postCard) continue;
                if(inSeen(postCard)) continue;
                seenCards.push(postCard);
                results.push({el: postCard, text: contentText});
            }
            return results;
            """

            while len(self.posts) < limit and scroll < max_scroll and not self._stop_flag:
                before_count = len(self.posts)

                # Bấm tất cả nút "Xem thêm" / "See more" hiện có trên trang trước khi quét
                try:
                    see_more_btns = self.driver.find_elements(
                        By.XPATH,
                        '//*[@role="button" and (contains(.,"Xem thêm") or contains(.,"See more"))]'
                    )
                    for smb in see_more_btns:
                        try:
                            self.driver.execute_script("arguments[0].click()", smb)
                        except Exception:
                            pass
                    if see_more_btns:
                        time.sleep(0.5)
                except Exception:
                    pass

                # Dùng JS: 3 chiến lược tìm bài có từ khoá
                # Diagnostic vòng đầu: kiểm tra page_source + body.innerText
                if scroll == 0:
                    try:
                        _src = self.driver.page_source
                        _src_ok = any(p.search(_src) for p, _ in rules)
                        _it = self.driver.execute_script(
                            "return (document.body&&document.body.innerText)||'';"
                        ) or ""
                        _it_ok = any(p.search(_it) for p, _ in rules)
                        _n_art = len(self.driver.find_elements(By.XPATH, "//div[@role='article']"))
                        self._log(
                            f"  [debug] page_source={_src_ok} | body.innerText={_it_ok} | articles={_n_art}",
                            "info",
                        )
                    except Exception:
                        pass

                try:
                    js_result = self.driver.execute_script(JS_FIND, js_keywords, js_skip) or {}
                    # Parse new format (dict with 'posts') or old format (list)
                    found_items = js_result.get('posts', []) if isinstance(js_result, dict) else js_result
                except Exception:
                    found_items = []

                self._log(f"🔍  Vòng quét {scroll + 1}: tìm thấy {len(found_items)} bài khớp.", "info")

                for item in found_items:
                    if len(self.posts) >= limit:
                        break
                    try:
                        el       = item["el"]
                        text     = (item.get("text") or "").strip()
                        menu_btn = item.get("menuBtn")  # nút "..." cụ thể tìm được từ JS
                        if not text:
                            continue
                        eid = el.id
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)

                        preview = text[:70].replace("\n", " ")
                        self.posts.append({"el": el, "text": text, "menuBtn": menu_btn})
                        self._log(
                            f"  [{len(self.posts)}] Tìm thấy bài cần sửa: {preview}...",
                            "warn",
                        )
                    except Exception:
                        continue

                # Nếu sau vòng này không tìm thêm bài mới, tăng idle_rounds
                if len(self.posts) == before_count:
                    idle_rounds += 1
                else:
                    idle_rounds = 0

                # Nếu đã cuộn vài lần mà không có bài mới → dừng sớm
                if idle_rounds >= 4:
                    self._log("ℹ  Đã cuộn nhiều lần nhưng không thấy thêm bài phù hợp, dừng sớm.", "info")
                    break

                # Cuộn tiếp để tải thêm bài
                self.driver.execute_script("window.scrollBy(0, 1400)")
                time.sleep(2.5)
                scroll += 1
                self.progress["value"] = min(95, int(scroll / max_scroll * 100))

            self.progress["value"] = 100
            self._log(f"✅  Xong! Tìm thấy {len(self.posts)} bài cần sửa.", "ok")

        except Exception as e:
            self._log(f"❌  Lỗi khi tải bài: {e}", "err")

    # ══════════════════════════════════════════════════════════════════════════
    # Selenium – Tự động sửa bài
    # ══════════════════════════════════════════════════════════════════════════
    def _do_fix_all(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập trước!")
            return
        if not self.posts:
            messagebox.showinfo("Chưa tải bài", "Nhấn «Tải bài đăng» trước!")
            return
        self._stop_flag = False
        threading.Thread(target=self._fix_all_thread, daemon=True).start()

    def _fix_all_thread(self):
        # Đọc quy tắc từ UI
        rules = self._get_rules_from_ui()
        if not rules:
            self._log("⚠  Không có quy tắc nào được nhập. Vui lòng nhập quy tắc trước khi sửa.", "err")
            return
        
        total   = len(self.posts)
        fixed   = 0
        skipped = 0

        for i, post in enumerate(self.posts, 1):
            if self._stop_flag:
                self._log("⏹  Đã dừng.", "warn")
                break

            self.progress["value"] = int(i / total * 100)
            self._log(f"─── Bài {i}/{total} ───", "info")

            try:
                el           = post["el"]   # = post card (role=article hoặc container có nút "...")
                new_text, count = apply_rules(post["text"], rules)

                if count == 0:
                    self._log("  ↷  Không cần sửa.", "info")
                    skipped += 1
                    continue

                # Kiểm tra element còn hợp lệ không (tránh StaleElement)
                try:
                    _ = el.tag_name
                except Exception:
                    self._log("  ↷  Bài đã mất khỏi DOM (stale), bỏ qua.", "warn")
                    skipped += 1
                    continue

                # Cuộn post card vào giữa màn hình
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'})", el)
                time.sleep(1.2)

                # Hover vào post card để Facebook hiện nút "..."
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).move_to_element(el).perform()
                    time.sleep(0.8)
                except Exception:
                    pass

                # Tìm nút "..." (post options) trong post card bằng XPath
                # BỎ QUA nút settings/profile (aria-label chứa "cài đặt" hoặc "trang cá nhân")
                menu_btn = None
                try:
                    candidates = el.find_elements(
                        By.XPATH,
                        './/*[@aria-haspopup="menu" and (@role="button" or not(@role))]'
                    )
                    for cand in candidates:
                        try:
                            label = cand.get_attribute("aria-label") or ""
                            # Bỏ qua nút settings/profile
                            if any(x in label.lower() for x in ["cài đặt", "settings", "trang cá nhân", "profile", "quản lý trang"]):
                                continue
                            # Nút hợp lệ
                            menu_btn = cand
                            break
                        except Exception:
                            pass
                    
                    # Nếu không tìm được bằng cách lọc, thử các aria-label cụ thể
                    if menu_btn is None:
                        menu_btn = self._find_first_xpath(
                            el,
                            [
                                './/*[@aria-label="Actions for this post"]',
                                './/*[@aria-label="Story options"]',
                                './/*[contains(@aria-label,"Thêm tùy chọn") and @aria-haspopup="menu"]',
                            ],
                        )
                except Exception:
                    pass
                if menu_btn is None:
                    self._log("  ⚠  Không tìm được nút menu '...', bỏ qua.", "err")
                    skipped += 1
                    continue

                # Log debug: tag và aria-label của nút tìm được
                try:
                    btn_tag   = menu_btn.tag_name
                    btn_label = menu_btn.get_attribute("aria-label") or ""
                    self._log(f"  [dbg] menu_btn: <{btn_tag}> aria-label='{btn_label}'", "info")
                except Exception:
                    pass

                try:
                    self.driver.execute_script("arguments[0].click()", menu_btn)
                except Exception:
                    try:
                        menu_btn.click()
                    except Exception as e:  # noqa: BLE001
                        self._log(f"  ⚠  Không bấm được nút menu: {e}", "err")
                        skipped += 1
                        continue

                time.sleep(1.5)

                # Nhấn "Chỉnh sửa bài viết" trong menu (tiếng Việt hoặc Anh)
                # Nếu không có = bình luận của người khác → bỏ qua ngay, đóng menu
                _edit_found = False
                try:
                    edit_xpath = (
                        '//*[(@role="menuitem" or @role="button" or @role="none") and '
                        '(contains(.,"Chỉnh sửa bài viết") or contains(.,"Sửa bài viết") or '
                        'contains(.,"Chỉnh sửa bài đăng") or contains(.,"Chỉnh sửa") or '
                        'contains(.,"Edit post") or contains(.,"Edit"))]'
                    )
                    edit_item = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH, edit_xpath))
                    )
                    edit_item.click()
                    _edit_found = True
                except Exception:
                    # Không có "Chỉnh sửa" trong menu → đây là bình luận / bài của người khác
                    # Đóng menu bằng Escape rồi bỏ qua
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    self._log("  ↷  Bỏ qua (bình luận/bài người khác, không có quyền sửa).", "info")
                    skipped += 1
                    continue
                time.sleep(2)

                # Lấy dialog popup chỉnh sửa bài (tránh nhầm với ô bình luận ngoài trang)
                try:
                    dialog = WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located((By.XPATH, '//div[@role="dialog"]'))
                    )
                except Exception:
                    dialog = self.driver  # fallback: dùng toàn trang nếu không có dialog

                # Lấy vùng soạn thảo bên TRONG dialog
                editor_xpath = './/div[@contenteditable="true" and @role="textbox"]'
                editor = WebDriverWait(self.driver, 8).until(
                    lambda d: dialog.find_element(By.XPATH, editor_xpath)
                )
                # Dùng JS click để tránh bị element khác chặn
                self.driver.execute_script("arguments[0].click()", editor)
                time.sleep(0.5)

                # Đọc nội dung THỰC TẾ từ editor (đáng tin cậy hơn text quét được)
                try:
                    actual_editor_text = self.driver.execute_script(
                        "return arguments[0].innerText || arguments[0].textContent || '';",
                        editor
                    ) or ""
                    actual_new_text, actual_count = apply_rules(actual_editor_text, rules)
                    if actual_count > 0:
                        new_text = actual_new_text
                        count = actual_count
                    elif count == 0:
                        # Cả scanned text lẫn editor text đều không cần sửa
                        try:
                            from selenium.webdriver.common.action_chains import ActionChains
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                        except Exception:
                            pass
                        self._log("  ↷  Editor không có nội dung cần sửa, bỏ qua.", "info")
                        skipped += 1
                        continue
                except Exception:
                    pass  # Dùng new_text từ scan nếu đọc editor thất bại

                # Xoá hết, gõ lại nội dung mới
                editor.send_keys(Keys.CONTROL + "a")
                time.sleep(0.3)
                editor.send_keys(new_text)
                time.sleep(1)

                # Nhấn Lưu / Cập nhật / Save – tìm bên trong dialog trước
                try:
                    save_xpath_in_dialog = (
                        './/div[@role="button" and ('
                        '@aria-label="Save" or @aria-label="Lưu" or '
                        '@aria-label="Cập nhật" or @aria-label="Update" or '
                        'contains(.,"Lưu") or contains(.,"Save") or '
                        'contains(.,"Cập nhật") or contains(.,"Update"))]'
                    )
                    save_btn = WebDriverWait(self.driver, 10).until(
                        lambda d: dialog.find_element(By.XPATH, save_xpath_in_dialog)
                    )
                    self.driver.execute_script("arguments[0].click()", save_btn)
                except Exception as e:  # noqa: BLE001
                    # Fallback: quét toàn trang
                    try:
                        all_btns = self.driver.find_elements(By.XPATH, '//*[@role="button"]')
                        save_btn = None
                        for b in all_btns:
                            try:
                                txt = (b.text or "").lower()
                                lbl = (b.get_attribute("aria-label") or "").lower()
                            except Exception:
                                continue
                            if any(k in txt or k in lbl for k in ["lưu", "save", "cập nhật", "update"]):
                                save_btn = b
                                break
                        if save_btn is None:
                            raise e
                        self.driver.execute_script("arguments[0].click()", save_btn)
                    except Exception:
                        self._log(f"  ⚠  Không tìm được nút Lưu/Cập nhật: {e}", "err")
                        skipped += 1
                        continue
                time.sleep(2.5)

                self._log(f"  ✅  Đã sửa {count} chỗ.", "ok")
                fixed += 1

            except Exception as e:
                import traceback
                err_type = type(e).__name__
                self._log(f"  ⚠  Lỗi bài này ({err_type}): {str(e)[:120]}", "err")
                if "stale" in str(e).lower() or "stale" in err_type.lower():
                    self._log("     → Element đã mất khỏi DOM (cuộn trang), bỏ qua bài này.", "warn")
                skipped += 1
                # Đóng dialog nếu còn mở
                try:
                    self.driver.find_element(
                        By.XPATH, '//div[@aria-label="Close" or @aria-label="Đóng"]'
                    ).click()
                except Exception:
                    pass
                time.sleep(1)

        self.progress["value"] = 100
        self._log(
            f"🏁  Hoàn thành! Đã sửa: {fixed} | Bỏ qua: {skipped} / Tổng: {total} bài.",
            "ok"
        )

    def _do_stop(self):
        self._stop_flag = True
        self._log("⏹  Đang dừng...", "warn")

    # ══════════════════════════════════════════════════════════════════════════
    # Helper: parse rules từ UI
    # ══════════════════════════════════════════════════════════════════════════
    def _get_rules_from_ui(self):
        """Đọc quy tắc từ rules_text và trả về [(re.Pattern, replacement), ...]"""
        raw_text = self.rules_text.get("1.0", "end-1c")
        rules = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if not line or "=>" not in line:
                continue
            parts = line.split("=>", 1)
            if len(parts) != 2:
                continue
            find_str = parts[0].strip()
            replace_str = parts[1].strip()
            if find_str:
                try:
                    pattern = re.compile(find_str, re.IGNORECASE)
                    rules.append((pattern, replace_str))
                except Exception:
                    # Bỏ qua quy tắc regex không hợp lệ
                    pass
        return rules

    # ══════════════════════════════════════════════════════════════════════════
    # Auto Comment Tab Methods
    # ══════════════════════════════════════════════════════════════════════════
    
    def _fetch_groups(self):
        """Fetch list of joined Facebook groups (cho tab Auto Comment)."""
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        self._log("🔄 Đang tải danh sách nhóm (tất cả nhóm bạn tham gia)...", "info")
        threading.Thread(target=self._fetch_groups_worker, args=(False,), daemon=True).start()

    def _fetch_groups_worker(self, managers_only=False):
        try:
            # Navigate to groups page
            # Use Groups Feed view because it reliably shows the left "Nhóm của tôi" sidebar
            self.driver.get("https://www.facebook.com/groups/feed/")
            time.sleep(3)
            
            # Scroll in LEFT SIDEBAR (not main feed) to load ALL groups
            self._log("  📜 Cuộn khung bên trái để tải nhóm...", "info")
            
            # Find the left sidebar by anchoring on "My groups" headings (more stable than roles)
            find_sidebar_js = """
            function findScrollableAncestor(node) {
                var cur = node;
                for (var depth = 0; depth < 12 && cur; depth++) {
                    try {
                        var rect = cur.getBoundingClientRect();
                        if (rect.left < 450 && rect.width < 520 && cur.scrollHeight > cur.clientHeight + 40) {
                            return cur;
                        }
                    } catch (e) {}
                    cur = cur.parentElement;
                }
                return null;
            }

            var needles = [
                'Nhóm do bạn quản lý',
                'Nhóm bạn đã tham gia',
                'Your groups',
                'Groups you manage',
                "Groups you've joined"
            ];

            var candidates = Array.from(document.querySelectorAll('div, span, h2, h3'));
            for (var i = 0; i < candidates.length; i++) {
                var t = (candidates[i].innerText || '').trim();
                if (!t) continue;
                for (var j = 0; j < needles.length; j++) {
                    if (t.indexOf(needles[j]) !== -1) {
                        var sidebar = findScrollableAncestor(candidates[i]);
                        if (sidebar) return sidebar;
                    }
                }
            }

            // Fallback: any scrollable container on the left
            var all = Array.from(document.querySelectorAll('div'));
            for (var k = 0; k < all.length; k++) {
                try {
                    var rect2 = all[k].getBoundingClientRect();
                    if (rect2.left < 450 && rect2.width < 520 && all[k].scrollHeight > all[k].clientHeight + 120) {
                        return all[k];
                    }
                } catch (e2) {}
            }
            return null;
            """
            
            # Try to get sidebar element
            sidebar_elem = None
            try:
                sidebar_elem = self.driver.execute_script(find_sidebar_js)
            except:
                pass

            def _refresh_sidebar():
                try:
                    return self.driver.execute_script(find_sidebar_js)
                except Exception:
                    return None
            
            # Scroll sidebar or entire page
            if sidebar_elem:
                self._log("  ✅ Đã tìm thấy sidebar - đang cuộn...", "info")
                try:
                    sidebar_info = self.driver.execute_script(
                        "var r=arguments[0].getBoundingClientRect(); return {left:r.left, width:r.width, sh:arguments[0].scrollHeight, ch:arguments[0].clientHeight};",
                        sidebar_elem,
                    )
                    if isinstance(sidebar_info, dict):
                        self._log(
                            f"  ℹ Sidebar left={sidebar_info.get('left', 0):.0f} w={sidebar_info.get('width', 0):.0f} scroll={sidebar_info.get('sh', 0)}",
                            "info",
                        )
                except Exception:
                    pass
                # Scroll the sidebar để FB load thêm nhóm.
                # Với chế độ chỉ lấy nhóm DO BẠN QUẢN LÝ, các nhóm này thường nằm ngay trên đầu,
                # nên không cần cuộn quá sâu (tránh mất thời gian).
                stable_rounds = 0
                last_link_count = -1
                last_scroll_height = -1
                last_scroll_top = -1
                max_rounds = 140
                if managers_only:
                    # Giới hạn vòng cuộn khi chỉ cần nhóm quản trị (đủ để mở "Xem thêm").
                    max_rounds = 24

                for round_idx in range(max_rounds):
                    # Click "Xem thêm" / "See more" inside sidebar if present
                    try:
                        clicked_more = self.driver.execute_script(
                            """
                            var sidebar = arguments[0];
                            if (!sidebar) return false;
                            var nodes = sidebar.querySelectorAll('[role="button"], a');
                            for (var i=0;i<nodes.length;i++) {
                                var t = (nodes[i].innerText || nodes[i].textContent || '').trim().toLowerCase();
                                // Some UIs show "Xem thêm ▼" or include extra whitespace
                                if (t.indexOf('xem thêm') !== -1 || t.indexOf('see more') !== -1) {
                                    nodes[i].scrollIntoView({block:'center'});
                                    nodes[i].click();
                                    return true;
                                }
                            }
                            return false;
                            """,
                            sidebar_elem,
                        )
                        if clicked_more:
                            time.sleep(0.8)
                    except Exception:
                        pass

                    # Scroll down progressively (virtualized lists often need incremental scroll)
                    try:
                        stats = self.driver.execute_script(
                            """
                            var sidebar = arguments[0];
                            if (!sidebar) return {ok:false};
                            var beforeTop = sidebar.scrollTop;
                            sidebar.scrollTop = beforeTop + Math.max(500, Math.floor(sidebar.clientHeight * 0.85));
                            try { sidebar.dispatchEvent(new Event('scroll', {bubbles:true})); } catch(e) {}
                            var links = sidebar.querySelectorAll('a[href*="/groups/"]');
                            return {
                                ok:true,
                                linkCount: links.length,
                                scrollHeight: sidebar.scrollHeight,
                                scrollTop: sidebar.scrollTop,
                                clientHeight: sidebar.clientHeight,
                                beforeTop: beforeTop
                            };
                            """,
                            sidebar_elem,
                        )
                    except Exception as e:
                        if "stale" in str(e).lower():
                            sidebar_elem = _refresh_sidebar()
                        stats = None
                        stats = None

                    time.sleep(0.9)

                    if isinstance(stats, dict) and stats.get('ok'):
                        link_count = int(stats.get('linkCount', 0))
                        sh = int(stats.get('scrollHeight', 0))
                        st = int(stats.get('scrollTop', 0))
                        bt = int(stats.get('beforeTop', 0))
                        ch = int(stats.get('clientHeight', 0))

                        at_bottom = (st + ch + 5) >= sh
                        did_move = st != bt

                        if (round_idx + 1) % 8 == 0:
                            self._log(f"  ⏳ Sidebar links={link_count} rounds={round_idx + 1}", "info")

                        # Only consider stable when we are at bottom OR can't move further
                        if (not did_move) and (link_count == last_link_count) and (sh == last_scroll_height):
                            stable_rounds += 1
                        elif at_bottom and (link_count == last_link_count) and (sh == last_scroll_height) and (st == last_scroll_top):
                            stable_rounds += 1
                        else:
                            stable_rounds = 0
                        last_link_count = link_count
                        last_scroll_height = sh
                        last_scroll_top = st

                        # Với tất cả nhóm: đợi tới khi cuộn chạm đáy và ổn định lâu.
                        # Với chỉ nhóm quản trị: ưu tiên tốc độ, dừng sau ~10 vòng đầu tiên.
                        if managers_only:
                            if (round_idx + 1) >= 10:
                                break
                        else:
                            # Don't stop too early; allow FB to lazy-load
                            if (round_idx + 1) >= 24 and stable_rounds >= 8:
                                break

                self._log("  ✅ Đã cuộn sidebar đến khi ổn định", "info")
            else:
                self._log("  📜 Không tìm thấy sidebar - cuộn toàn trang...", "info")
                scroll_count = 20
                for scroll_idx in range(scroll_count):
                    self.driver.execute_script("window.scrollBy(0, 1200);")
                    time.sleep(1.2)
                    
                    # Log progress
                    if (scroll_idx + 1) % 5 == 0:
                        self._log(f"  ⏳ Đang tải... ({scroll_idx + 1}/{scroll_count})", "info")
            
            # Final scroll to bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Extract groups - có thể lọc chỉ các nhóm bạn quản lý
            groups_js = """
            var groups = [];
            var seen = new Set();

            var onlyManaged = !!arguments[1];

            // If a sidebar element is provided, prefer extracting from it
            var root = arguments[0] || document;

            // Xác định khoảng toạ độ Y cho khu vực "Nhóm do bạn quản lý"
            var managedTop = null;
            var managedBottom = null;
            if (onlyManaged) {
                try {
                    var labels = root.querySelectorAll('div, span');
                    for (var i = 0; i < labels.length; i++) {
                        var t = (labels[i].innerText || '').toLowerCase().trim();
                        if (!t) continue;
                        if (t.indexOf('nhóm do bạn quản lý') !== -1 || t.indexOf('groups you manage') !== -1) {
                            var r1 = labels[i].getBoundingClientRect();
                            managedTop = r1.top - 5;
                            // Tìm tiêu đề tiếp theo "Nhóm bạn đã tham gia / Groups you've joined" để làm đáy
                            for (var j = i + 1; j < labels.length; j++) {
                                var t2 = (labels[j].innerText || '').toLowerCase().trim();
                                if (!t2) continue;
                                if (t2.indexOf('nhóm bạn đã tham gia') !== -1 || t2.indexOf("groups you've joined") !== -1) {
                                    var r2 = labels[j].getBoundingClientRect();
                                    managedBottom = r2.top - 5;
                                    break;
                                }
                            }
                            break;
                        }
                    }
                } catch (e) {}
            }

            var allLinks = root.querySelectorAll('a[href*="/groups/"]');

            allLinks.forEach(function(link) {
                try {
                    var href = link.href;

                    // Match numeric or vanity URL
                    var match = href.match(/\\/groups\\/(\\d+)/) || href.match(/\\/groups\\/([a-zA-Z0-9._-]+)/);
                    if (!match || !match[1]) return;

                    var groupId = match[1];

                    // Skip if already seen
                    if (seen.has(groupId)) return;

                    // Nếu chỉ lấy nhóm do bạn quản lý thì dùng toạ độ để lọc theo vùng
                    if (onlyManaged && managedTop !== null) {
                        var lr = link.getBoundingClientRect();
                        var cy = (lr.top + lr.bottom) / 2;
                        if (cy < managedTop) return;
                        if (managedBottom !== null && cy > managedBottom) return;
                    }

                    // Get link position - prefer left sidebar (x < 450)
                    var isLeftSidebar = true;
                    if (root === document) {
                        var rect = link.getBoundingClientRect();
                        isLeftSidebar = rect.left < 450;
                    }

                    // Get text content
                    var name = (link.textContent || '').trim();

                    // Skip navigation/system items
                    if (!name || name.length < 3 || name.length > 150) return;
                    if (name === 'Nhóm' || name === 'Groups' || name === 'Tìm kiếm' ||
                        name === 'Search' || name === 'Thông báo' || name === 'Notification' ||
                        name === 'Xem thêm' || name === 'See more' || name === 'Feed') return;

                    seen.add(groupId);
                    groups.push({
                        name: name,
                        url: 'https://www.facebook.com/groups/' + groupId,
                        isLeftSidebar: isLeftSidebar
                    });
                } catch(e) {
                    // Skip on error
                }
            });

            // Sort: left sidebar items first
            groups.sort(function(a, b) {
                if (a.isLeftSidebar && !b.isLeftSidebar) return -1;
                if (!a.isLeftSidebar && b.isLeftSidebar) return 1;
                return 0;
            });

            // Deduplicate by name
            var uniqueGroups = [];
            var seenNames = new Set();
            for (var i = 0; i < groups.length; i++) {
                var g = groups[i];
                if (!seenNames.has(g.name)) {
                    seenNames.add(g.name);
                    uniqueGroups.push({name: g.name, url: g.url});
                }
            }

            return uniqueGroups;
            """
            
            groups = self.driver.execute_script(groups_js, sidebar_elem, bool(managers_only)) or []

            if (not managers_only) and len(groups) < 100:
                try:
                    fallback_groups = self.driver.execute_script(groups_js, None, False) or []
                    if len(fallback_groups) > len(groups):
                        groups = fallback_groups
                        self._log(f"  ℹ Dùng danh sách nhóm mở rộng từ toàn trang: {len(groups)}", "info")
                except Exception:
                    pass
            
            if not groups:
                self._log("⚠️ Không tìm thấy nhóm nào. Thử cuộn thêm hoặc kiểm tra quyền truy cập.", "warn")
                return
            
            # Update UI: tuỳ theo chế độ gọi (tất cả nhóm hay chỉ nhóm quản lý)
            if managers_only:
                # Chỉ cập nhật tab duyệt bài nhóm
                self._update_approval_group_list(groups)
                self._log(f"✅ Đã tải {len(groups)} nhóm do bạn quản lý", "ok")
            else:
                # Chỉ cập nhật tab Auto Comment
                self._update_group_list(groups)
                self._log(f"✅ Đã tải {len(groups)} nhóm (tất cả nhóm bạn tham gia)", "ok")
            
        except Exception as e:
            self._log(f"❌ Lỗi khi tải nhóm: {e}", "err")
    
    def _update_group_list(self, groups, selected_set=None, update_source=True):
        """Update the scrollable group checkbox list."""
        if update_source:
            self.comment_groups_all = list(groups or [])

        # Clear existing checkboxes
        for widget in self.group_list_frame.winfo_children():
            widget.destroy()
        self.selected_groups.clear()

        if selected_set is None:
            if self.comment_selected_urls:
                selected_set = set(self.comment_selected_urls)
            else:
                selected_set = set(self._pending_selected_group_urls or [])
        else:
            selected_set = set(selected_set)

        if update_source:
            self.comment_selected_urls = set(selected_set)
        
        # Add checkboxes for each group
        for idx, group in enumerate(groups):
            var = tk.BooleanVar(value=group.get('url') in selected_set)
            self.selected_groups[group['url']] = {'var': var, 'name': group['name']}
            
            # Show full name if short, truncate if long
            display_name = group['name'] if len(group['name']) <= 80 else f"{group['name'][:77]}..."
            
            chk = tk.Checkbutton(self.group_list_frame, 
                                text=display_name,
                                variable=var,
                                font=FONT, bg=BG_PANEL, fg=FG_LIGHT,
                                activebackground=BG_PANEL, activeforeground=ACCENT,
                                selectcolor=BG_PANEL, anchor="w", wraplength=900,
                                command=self._on_comment_group_selection_changed)  # Wrap long names
            chk.pack(fill="x", padx=10, pady=1)  # Reduced padding for compact list
        
        # Log summary
        self._log(f"  📋 Hiển thị {len(groups)} nhóm trong danh sách", "info")
        self._update_comment_selected_count()

        # Cache scanned groups for next launch (tied to current FB account)
        if update_source:
            try:
                selected_urls = list(self.comment_selected_urls)
                self._save_group_cache(self.comment_groups_cache_file, self.comment_groups_all, selected_urls)
                self._pending_selected_group_urls.clear()
            except Exception:
                pass

        # Sync to group-post tab (reuse same group list)
        try:
            if getattr(self, "group_post_list_frame", None) is not None:
                self._update_group_post_list(self.comment_groups_all, selected_set=self.group_post_selected_urls, update_source=True)
        except Exception:
            pass
    
    def _toggle_all_groups(self, select):
        """Select or deselect all groups."""
        for group_data in self.selected_groups.values():
            group_data['var'].set(select)
        self._on_comment_group_selection_changed()

    def _fetch_groups_for_approval(self):
        """Tải nhóm RIÊNG cho tab duyệt bài (chỉ nhóm bạn quản lý)."""
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        self._log("🔄 Đang tải danh sách NHÓM DO BẠN QUẢN LÝ...", "info")
        threading.Thread(target=self._fetch_groups_worker, args=(True,), daemon=True).start()

    # --- Group list helpers for approval tab ---
    def _update_approval_group_list(self, groups):
        """Update checkbox list for approval tab (reuses same group source)."""
        if not self.approval_group_list_frame:
            return

        for widget in self.approval_group_list_frame.winfo_children():
            widget.destroy()
        self.approval_selected_groups.clear()

        for group in groups:
            var = tk.BooleanVar(value=group.get('url') in self._pending_selected_approval_urls)
            self.approval_selected_groups[group['url']] = {'var': var, 'name': group['name']}

            display_name = group['name'] if len(group['name']) <= 80 else f"{group['name'][:77]}..."
            chk = tk.Checkbutton(
                self.approval_group_list_frame,
                text=display_name,
                variable=var,
                font=FONT,
                bg=BG_PANEL,
                fg=FG_LIGHT,
                activebackground=BG_PANEL,
                activeforeground=ACCENT,
                selectcolor=BG_PANEL,
                anchor="w",
                wraplength=900,
                command=self._on_approval_group_selection_changed,
            )
            chk.pack(fill="x", padx=10, pady=1)

        self._log(f"  📋 Hiển thị {len(groups)} nhóm trong tab duyệt bài", "info")
        self.managed_group_urls = set(self.approval_selected_groups.keys())
        try:
            selected_urls = [url for url, data in self.approval_selected_groups.items() if data['var'].get()]
            self._save_group_cache(self.approval_groups_cache_file, groups, selected_urls)
            self._pending_selected_approval_urls = set()
        except Exception:
            pass

    def _toggle_all_approval_groups(self, select: bool):
        for group_data in self.approval_selected_groups.values():
            group_data['var'].set(select)
        self._on_approval_group_selection_changed()

    def _on_comment_group_selection_changed(self):
        try:
            visible_urls = set(self.selected_groups.keys())
            selected_visible = {url for url, data in self.selected_groups.items() if data['var'].get()}
            self.comment_selected_urls = (self.comment_selected_urls - visible_urls) | selected_visible

            if self.comment_groups_all:
                self._save_group_cache(self.comment_groups_cache_file, self.comment_groups_all, list(self.comment_selected_urls))
            self._log(f"✅ Đã chọn {len(self.comment_selected_urls)} nhóm (Auto Comment)", "info")
            self._update_comment_selected_count()
        except Exception:
            pass

    def _update_comment_selected_count(self):
        try:
            cnt = len(self.comment_selected_urls) if self.comment_selected_urls else len(
                [1 for _url, data in self.selected_groups.items() if data['var'].get()]
            )
            self.comment_selected_count_var.set(f"Đã chọn: {cnt} nhóm")
        except Exception:
            pass

    def _update_group_post_list(self, groups, selected_set=None, update_source=True):
        if not getattr(self, "group_post_list_frame", None):
            return

        if update_source:
            self.group_post_groups_all = list(groups or [])

        for widget in self.group_post_list_frame.winfo_children():
            widget.destroy()
        self.group_post_selected_groups.clear()

        if selected_set is None:
            selected_set = set(self.group_post_selected_urls or [])
        else:
            selected_set = set(selected_set)

        if update_source:
            self.group_post_selected_urls = set(selected_set)

        for group in groups:
            var = tk.BooleanVar(value=group.get('url') in selected_set)
            self.group_post_selected_groups[group['url']] = {'var': var, 'name': group['name']}
            display_name = group['name'] if len(group['name']) <= 80 else f"{group['name'][:77]}..."
            if self.group_post_pending_required.get(group.get("url")) is True:
                display_name = f"{display_name}  [Cần duyệt]"
            chk = tk.Checkbutton(
                self.group_post_list_frame,
                text=display_name,
                variable=var,
                font=FONT,
                bg=BG_PANEL,
                fg=FG_LIGHT,
                activebackground=BG_PANEL,
                activeforeground=ACCENT,
                selectcolor=BG_PANEL,
                anchor="w",
                wraplength=900,
                command=self._on_group_post_selection_changed,
            )
            chk.pack(fill="x", padx=10, pady=1)

        self._log(f"  📋 Hiển thị {len(groups)} nhóm trong tab đăng bài", "info")
        self._update_group_post_selected_count()

        if update_source:
            try:
                selected_urls = list(self.group_post_selected_urls)
                self._save_group_cache(self.group_post_groups_cache_file, self.group_post_groups_all, selected_urls)
            except Exception:
                pass

    def _toggle_all_group_post(self, select: bool):
        for group_data in self.group_post_selected_groups.values():
            group_data['var'].set(select)
        self._on_group_post_selection_changed()

    def _on_group_post_selection_changed(self):
        try:
            visible_urls = set(self.group_post_selected_groups.keys())
            selected_visible = {url for url, data in self.group_post_selected_groups.items() if data['var'].get()}
            self.group_post_selected_urls = (self.group_post_selected_urls - visible_urls) | selected_visible

            if self.group_post_groups_all:
                self._save_group_cache(self.group_post_groups_cache_file, self.group_post_groups_all, list(self.group_post_selected_urls))
            self._log(f"✅ Đã chọn {len(self.group_post_selected_urls)} nhóm (Đăng bài nhóm)", "info")
            self._update_group_post_selected_count()
        except Exception:
            pass

    def _update_group_post_selected_count(self):
        try:
            self.group_post_selected_count_var.set(f"Đã chọn: {len(self.group_post_selected_urls)} nhóm")
        except Exception:
            pass

    def _set_group_post_pending_required(self, group_url, required):
        try:
            self.group_post_pending_required[str(group_url)] = bool(required)
            if getattr(self, "group_post_list_frame", None) is not None:
                self._update_group_post_list(self.group_post_groups_all, selected_set=self.group_post_selected_urls, update_source=False)
        except Exception:
            pass

    def _scan_group_post_pending_for_groups(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        if not self.driver:
            messagebox.showwarning("Chưa mở Chrome", "Vui lòng mở Chrome và đăng nhập trước!")
            return

        selected = [url for url, data in self.group_post_selected_groups.items() if data['var'].get()]
        if not selected:
            selected = [g.get("url") for g in (self.group_post_groups_all or []) if g.get("url")]
        if not selected:
            messagebox.showwarning("Chưa có nhóm", "Vui lòng tải danh sách nhóm trước!")
            return

        threading.Thread(target=self._scan_group_post_pending_worker, args=(selected,), daemon=True).start()

    def _scan_group_post_pending_worker(self, group_urls):
        try:
            self._log(f"🔎 [Nhóm] Đang quét kiểm duyệt cho {len(group_urls)} nhóm...", "info")
            for idx, group_url in enumerate(group_urls, 1):
                if self.group_post_stop_event.is_set() or self.group_post_schedule_stop_event.is_set():
                    break
                required = self._detect_group_post_requires_approval(group_url)
                if required is None:
                    self._log(f"  ⚠️ [Nhóm] Không xác định kiểm duyệt: {group_url}", "warn")
                    continue
                self._set_group_post_pending_required(group_url, required)
                if required:
                    self._log(f"  🧷 [Nhóm] Cần kiểm duyệt: {group_url}", "info")
                else:
                    self._log(f"  ✅ [Nhóm] Cho đăng ngay: {group_url}", "info")
                if idx % 8 == 0:
                    time.sleep(1.0)
            self._log("✅ [Nhóm] Quét kiểm duyệt xong.", "ok")
        except Exception as e:
            self._log(f"❌ [Nhóm] Lỗi quét kiểm duyệt: {e}", "err")

    def _detect_group_post_requires_approval(self, group_url):
        if not self.driver:
            return None
        try:
            self.driver.get(group_url)
            time.sleep(3)
        except Exception:
            return None

        try:
            self._close_all_dialogs(aggressive=False)
        except Exception:
            pass

        try:
            hit = self.driver.execute_script(
                """
                function norm(s){ return (s||'').toLowerCase(); }
                var t = norm(document.body && (document.body.innerText || document.body.textContent) || '');
                if (!t) return '';
                var needles = [
                    'bài viết cần phê duyệt',
                    'bài viết của bạn đang chờ phê duyệt',
                    'bài viết của bạn sẽ được phê duyệt',
                    'bài viết sẽ được phê duyệt',
                    'bài viết đang chờ',
                    'đang chờ phê duyệt',
                    'chờ phê duyệt',
                    'posts must be approved',
                    'post must be approved',
                    'require approval',
                    'requires approval',
                    'admin approval',
                    'post is pending',
                    'pending post'
                ];
                for (var i=0;i<needles.length;i++){
                    if (t.indexOf(needles[i]) !== -1) return needles[i];
                }
                return '';
                """
            )
        except Exception:
            hit = ""

        if hit is None:
            return None
        return bool(hit)

    def _apply_group_post_filter(self):
        try:
            term_raw = (self.group_post_search_var.get() or "").strip()
            if not self.group_post_groups_all:
                return
            if not term_raw:
                filtered = list(self.group_post_groups_all)
            else:
                term = self._normalize_search_text(term_raw)
                tokens = [t for t in term.split() if t]

                def _matches(name, url):
                    n = self._normalize_search_text(name)
                    u = self._normalize_search_text(url)
                    if term in n or term in u:
                        return True
                    if tokens:
                        return all(any(tok in part for part in n.split()) for tok in tokens)
                    return self._is_subsequence(term, n)

                filtered = [
                    g for g in self.group_post_groups_all
                    if _matches(g.get("name", ""), g.get("url", ""))
                ]
            self._update_group_post_list(filtered, selected_set=self.group_post_selected_urls, update_source=False)
        except Exception:
            pass

    def _clear_group_post_list(self):
        try:
            if getattr(self, "group_post_list_frame", None) is None:
                return
            for widget in self.group_post_list_frame.winfo_children():
                widget.destroy()
            self.group_post_selected_groups.clear()
            self.group_post_groups_all = []
            self.group_post_selected_urls = set()
            self._update_group_post_selected_count()
        except Exception:
            pass

    def _choose_group_post_image(self, idx):
        filename = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")]
        )
        if filename:
            try:
                self.group_post_slots[idx]["image"].set(filename)
                self._log(f"📷 [Nhóm] Đã chọn ảnh mẫu {idx+1}: {os.path.basename(filename)}", "info")
            except Exception:
                pass

    def _apply_comment_group_filter(self):
        try:
            term_raw = (self.comment_group_search_var.get() or "").strip()
            if not self.comment_groups_all:
                return
            if not term_raw:
                filtered = list(self.comment_groups_all)
            else:
                term = self._normalize_search_text(term_raw)
                tokens = [t for t in term.split() if t]

                def _matches(name, url):
                    n = self._normalize_search_text(name)
                    u = self._normalize_search_text(url)
                    # Exact contains
                    if term in n or term in u:
                        return True
                    # Token partial match
                    if tokens:
                        return all(any(tok in part for part in n.split()) for tok in tokens)
                    # Fuzzy subsequence
                    return self._is_subsequence(term, n)

                filtered = [
                    g for g in self.comment_groups_all
                    if _matches(g.get("name", ""), g.get("url", ""))
                ]
            self._update_group_list(filtered, selected_set=self.comment_selected_urls, update_source=False)
        except Exception:
            pass

    def _normalize_search_text(self, text):
        try:
            t = (text or "").strip().lower()
            t = ''.join(ch for ch in unicodedata.normalize('NFD', t) if unicodedata.category(ch) != 'Mn')
            return t
        except Exception:
            return (text or "").strip().lower()

    def _is_subsequence(self, needle, haystack):
        if not needle:
            return True
        it = iter(haystack or "")
        return all(ch in it for ch in needle)

    def _on_approval_group_selection_changed(self):
        try:
            selected_urls = [url for url, data in self.approval_selected_groups.items() if data['var'].get()]
            groups = [{"name": v.get("name"), "url": k} for k, v in self.approval_selected_groups.items()]
            if groups:
                self._save_group_cache(self.approval_groups_cache_file, groups, selected_urls)
            self._log(f"✅ Đã chọn {len(selected_urls)} nhóm (Duyệt bài)", "info")
        except Exception:
            pass

    def _get_fb_user_id(self):
        """Return current FB user id via cookie (c_user), if available."""
        try:
            if not self.driver:
                return None
            return self.driver.execute_script(
                r"""
                var m = (document.cookie || '').match(/(?:^|;\s*)c_user=(\d+)/);
                return m ? m[1] : null;
                """
            )
        except Exception:
            return None

    def _save_group_cache(self, cache_file, groups, selected_urls):
        try:
            user_id = self._get_fb_user_id()
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            safe_groups = []
            for g in (groups or []):
                try:
                    safe_groups.append({
                        "name": str(g.get("name", "")),
                        "url": str(g.get("url", "")),
                    })
                except Exception:
                    continue
            safe_selected = []
            for u in (selected_urls or []):
                try:
                    safe_selected.append(str(u))
                except Exception:
                    continue
            payload = {
                "user_id": str(user_id) if user_id else None,
                "groups": safe_groups,
                "selected": safe_selected,
                "saved_at": dt.datetime.now().isoformat(),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            try:
                self._log(f"⚠️ Không thể lưu cache nhóm: {cache_file} ({e})", "warn")
            except Exception:
                pass

    def _load_group_cache(self, cache_file):
        try:
            if not os.path.exists(cache_file):
                return None
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _restore_comment_groups_cache(self):
        try:
            if not self.logged_in:
                return
            user_id = self._get_fb_user_id()
            if not user_id:
                return
            data = self._load_group_cache(self.comment_groups_cache_file)
            if not data:
                return
            if data.get("user_id") and (str(data.get("user_id")) != str(user_id)):
                self._clear_comment_group_list()
                self._log("⚠️ Tài khoản Facebook khác, không dùng danh sách nhóm đã lưu (Auto Comment).", "warn")
                return
            groups = data.get("groups") or []
            selected = set(data.get("selected") or [])
            if groups:
                self._update_group_list(groups, selected_set=selected)
                self._log(f"📂 Đã phục hồi {len(groups)} nhóm đã quét (Auto Comment)", "info")
                if not data.get("user_id"):
                    try:
                        self._save_group_cache(self.comment_groups_cache_file, groups, list(selected))
                    except Exception:
                        pass
        except Exception:
            pass

    def _restore_approval_groups_cache(self):
        try:
            if not self.logged_in:
                return
            user_id = self._get_fb_user_id()
            if not user_id:
                return
            data = self._load_group_cache(self.approval_groups_cache_file)
            if not data:
                return
            if data.get("user_id") and (str(data.get("user_id")) != str(user_id)):
                self._clear_approval_group_list()
                self._log("⚠️ Tài khoản Facebook khác, không dùng danh sách nhóm đã lưu (Duyệt bài).", "warn")
                return
            groups = data.get("groups") or []
            self._pending_selected_approval_urls = set(data.get("selected") or [])
            if groups:
                self._update_approval_group_list(groups)
                self._log(f"📂 Đã phục hồi {len(groups)} nhóm đã quét (Duyệt bài)", "info")
                if not data.get("user_id"):
                    try:
                        self._save_group_cache(self.approval_groups_cache_file, groups, list(self._pending_selected_approval_urls))
                    except Exception:
                        pass
        except Exception:
            pass

    def _restore_groups_cache_on_start(self):
        """Khôi phục danh sách nhóm đã quét trước đó ngay khi mở app (chưa xác thực tài khoản)."""
        try:
            data = self._load_group_cache(self.comment_groups_cache_file)
            if data:
                groups = data.get("groups") or []
                selected = set(data.get("selected") or [])
                if groups:
                    self._update_group_list(groups, selected_set=selected)
                    self._log(f"📂 Đã phục hồi {len(groups)} nhóm từ cache (Auto Comment)", "info")
        except Exception:
            pass

        try:
            data = self._load_group_cache(self.approval_groups_cache_file)
            if data:
                groups = data.get("groups") or []
                self._pending_selected_approval_urls = set(data.get("selected") or [])
                if groups:
                    self._update_approval_group_list(groups)
                    self._log(f"📂 Đã phục hồi {len(groups)} nhóm từ cache (Duyệt bài)", "info")
        except Exception:
            pass

        try:
            data = self._load_group_cache(self.group_post_groups_cache_file)
            if data:
                groups = data.get("groups") or []
                self.group_post_selected_urls = set(data.get("selected") or [])
                if groups and getattr(self, "group_post_list_frame", None) is not None:
                    self._update_group_post_list(groups, selected_set=self.group_post_selected_urls, update_source=True)
                    self._log(f"📂 Đã phục hồi {len(groups)} nhóm từ cache (Đăng bài nhóm)", "info")
        except Exception:
            pass

    def _clear_comment_group_list(self):
        try:
            for widget in self.group_list_frame.winfo_children():
                widget.destroy()
            self.selected_groups.clear()
            self.comment_groups_all = []
            self.comment_selected_urls = set()
            self._update_comment_selected_count()
            if getattr(self, "group_post_list_frame", None) is not None:
                self._clear_group_post_list()
        except Exception:
            pass

    def _clear_approval_group_list(self):
        try:
            if self.approval_group_list_frame:
                for widget in self.approval_group_list_frame.winfo_children():
                    widget.destroy()
            self.approval_selected_groups.clear()
            self.managed_group_urls = set()
        except Exception:
            pass
    
    def _choose_image(self):
        """Open file dialog to choose image."""
        filename = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")]
        )
        if filename:
            self.comment_image_path.set(filename)
            self._log(f"📷 Đã chọn ảnh: {os.path.basename(filename)}", "info")

    def _append_image_to_list(self):
        filenames = filedialog.askopenfilenames(
            title="Chọn nhiều ảnh",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif"), ("All files", "*.*")]
        )
        if not filenames:
            return
        if self.comment_images_box is None:
            return
        existing = self.comment_images_box.get("1.0", "end-1c").strip()
        lines = [line.strip() for line in existing.splitlines() if line.strip()] if existing else []
        for f in filenames:
            if f and f not in lines:
                lines.append(f)
        self.comment_images_box.delete("1.0", "end")
        self.comment_images_box.insert("1.0", "\n".join(lines))
        self._log(f"📷 Đã thêm {len(filenames)} ảnh vào danh sách", "info")

    def _clear_image_list(self):
        if self.comment_images_box is None:
            return
        self.comment_images_box.delete("1.0", "end")

    # ── Logic tự động duyệt bài nhóm ────────────────────────────────────────
    def _start_group_approval(self):
        """Bắt đầu luồng tự động duyệt/từ chối bài chờ duyệt trong nhóm."""
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        selected = [url for url, data in self.approval_selected_groups.items() if data['var'].get()]
        if not selected:
            messagebox.showwarning("Chưa chọn nhóm", "Vui lòng chọn ít nhất 1 nhóm để duyệt bài!")
            return

        keywords_text = ""
        try:
            if self.approval_keywords_box is not None:
                keywords_text = self.approval_keywords_box.get("1.0", "end-1c").strip()
        except Exception:
            keywords_text = ""

        blocked_keywords = [
            k.strip().lower()
            for k in keywords_text.splitlines()
            if k.strip()
        ]

        if not blocked_keywords and not self.approval_auto_approve_safe.get():
            messagebox.showwarning(
                "Thiếu tiêu chí",
                "Bạn chưa nhập từ khoá cũng như chưa bật tuỳ chọn phê duyệt bài an toàn.",
            )
            return

        # Chuẩn bị thread
        self.approval_stop_event.clear()

        mode = self.approval_mode_var.get()
        interval = max(1, int(self.approval_interval_var.get() or 1))

        self._set_run_buttons(self.btn_start_approval, self.btn_stop_approval, True, ACCENT, "#e74c3c")
        self._log(
            f"▶️ Bắt đầu auto duyệt bài cho {len(selected)} nhóm (chế độ: {mode}, chu kỳ {interval} phút)",
            "info",
        )

        args = (selected, blocked_keywords, mode, interval)
        self.approval_thread = threading.Thread(target=self._group_approval_worker, args=args, daemon=True)
        self.approval_thread.start()

    def _stop_group_approval(self):
        self.approval_stop_event.set()
        self._set_run_buttons(self.btn_start_approval, self.btn_stop_approval, False, ACCENT, "#e74c3c")
        self._log("⏹ Đã yêu cầu dừng auto duyệt bài", "warn")

    def _group_approval_worker(self, group_urls, blocked_keywords, mode, interval_minutes):
        """Worker chạy trong thread: quét bài chờ duyệt và xử lý theo tiêu chí."""
        try:
            cycle = 0
            while not self.approval_stop_event.is_set():
                cycle += 1
                self._log(f"🔁 [Duyệt bài] Chu kỳ #{cycle}", "info")
                for idx, group_url in enumerate(group_urls):
                    if self.approval_stop_event.is_set():
                        break

                    group_name = self.approval_selected_groups.get(group_url, {}).get('name', group_url)
                    self._log(
                        f"[{idx+1}/{len(group_urls)}] 🔍 Kiểm tra bài chờ duyệt trong nhóm: {group_name}",
                        "info",
                    )

                    try:
                        self._process_pending_posts_in_group(group_url, blocked_keywords)
                    except Exception as e:
                        self._log(f"❌ Lỗi khi duyệt bài trong nhóm {group_url}: {e}", "err")

                if mode == "once":
                    break

                # Chờ cho lần kế tiếp
                wait_seconds = max(60, int(interval_minutes) * 60)
                for _ in range(wait_seconds // 5):
                    if self.approval_stop_event.wait(5):
                        break
                if self.approval_stop_event.is_set():
                    break

        finally:
            self._log("🔕 Đã dừng auto duyệt bài nhóm", "warn")
            try:
                self.after(0, lambda: self._set_run_buttons(self.btn_start_approval, self.btn_stop_approval, False, ACCENT, "#e74c3c"))
            except Exception:
                pass

    def _process_pending_posts_in_group(self, group_url, blocked_keywords):
        """Mở trang nhóm, vào khu vực bài chờ duyệt và auto approve/deny."""
        if not self.driver:
            return

        if self._is_action_blocked():
            self._log("⛔ Facebook đang hạn chế thao tác, bỏ qua duyệt bài.", "err")
            return

        # Điều hướng tới trang bài chờ duyệt. Nhiều group dùng đường dẫn /pending_posts
        try:
            pending_url = group_url.rstrip("/") + "/pending_posts"
            self.driver.get(pending_url)
        except Exception:
            self.driver.get(group_url)

        # Chờ trang pending load rõ ràng hơn để tránh báo thiếu bài do load chậm
        time.sleep(2)
        pending_count_hint = None
        for _ in range(16):
            try:
                probe = self.driver.execute_script(
                    r"""
                    function txt(el){ return (el && (el.innerText || el.textContent) || '').trim(); }
                    function norm(s){ return (s||'').toLowerCase(); }

                    var bodyText = norm(document.body ? (document.body.innerText || '') : '');

                    // Tìm số ở tiêu đề kiểu: "Bài viết đang chờ · 2" hoặc "Pending posts · 2"
                    var pendingCount = null;
                    var candidates = Array.from(document.querySelectorAll('h1, h2, h3, span, div'));
                    for (var i = 0; i < candidates.length; i++) {
                        var t = txt(candidates[i]);
                        if (!t) continue;
                        var l = norm(t);
                        if (l.indexOf('bài viết đang chờ') !== -1 || l.indexOf('pending posts') !== -1) {
                            var m = t.match(/(\d+)/);
                            if (m && m[1]) { pendingCount = parseInt(m[1], 10); break; }
                        }
                    }

                    var approveRejectBtns = 0;
                    var nodes = Array.from(document.querySelectorAll('button, [role="button"]'));
                    for (var j = 0; j < nodes.length; j++) {
                        var b = norm(txt(nodes[j]));
                        if (!b) continue;
                        if (
                            b.indexOf('phê duyệt') !== -1 || b.indexOf('phe duyet') !== -1 || b.indexOf('approve') !== -1 ||
                            b.indexOf('từ chối') !== -1 || b.indexOf('tu choi') !== -1 || b.indexOf('decline') !== -1 || b.indexOf('reject') !== -1
                        ) {
                            approveRejectBtns++;
                        }
                    }

                    var articleCount = document.querySelectorAll('div[role="article"]').length;
                    return {
                        pendingCount: pendingCount,
                        approveRejectBtns: approveRejectBtns,
                        articleCount: articleCount,
                        hasPendingText: bodyText.indexOf('bài viết đang chờ') !== -1 || bodyText.indexOf('pending posts') !== -1
                    };
                    """
                ) or {}
            except Exception:
                probe = {}

            if isinstance(probe, dict):
                if probe.get("pendingCount") is not None:
                    try:
                        pending_count_hint = int(probe.get("pendingCount"))
                    except Exception:
                        pass

                # Trang đã sẵn sàng khi có nút duyệt/từ chối hoặc có article
                if int(probe.get("approveRejectBtns") or 0) > 0 or int(probe.get("articleCount") or 0) > 0:
                    break

                # Nếu có text pending_posts nhưng chưa render nút, chờ thêm
                if probe.get("hasPendingText"):
                    time.sleep(0.6)
                    continue

            time.sleep(0.6)

        if pending_count_hint is not None:
            self._log(f"  ℹ [Duyệt bài] Trang đang chờ duyệt báo: {pending_count_hint} bài", "info")

        # Cuộn nhẹ để FB load danh sách
        try:
            for _ in range(3):
                self.driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.0)
        except Exception:
            pass

        if self._is_action_blocked():
            self._log("⛔ Facebook đang hạn chế thao tác khi vào trang duyệt bài.", "err")
            return

        # Close stray dialogs/menus (e.g., notifications) that can hide toolbar buttons
        try:
            self._close_all_dialogs(aggressive=False)
        except Exception:
            pass

        from selenium.webdriver.common.action_chains import ActionChains

        def _find_pending_posts():
            posts_local = []
            try:
                # Giao diện cũ: mỗi bài là 1 div[role="article"]
                posts_local = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="article"]')
            except Exception:
                posts_local = []

            # Nếu không tìm thấy gì, thử giao diện mới: dò theo nút "Phê duyệt" / "Từ chối"
            if not posts_local:
                try:
                    posts_local = self.driver.execute_script(
                        """
                        function norm(s){ return (s||'').toLowerCase(); }

                        // Tìm tất cả các nút có text liên quan tới Phê duyệt / Từ chối
                        var btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                        var roots = [];
                        var seen = new Set();

                        function findRoot(el){
                            var cur = el;
                            // Đi lên tối đa 8 cấp để tìm khối bao quanh bài viết
                            for (var i=0; i<8 && cur; i++){
                                try {
                                    var role = (cur.getAttribute && cur.getAttribute('role')) || '';
                                    if (role === 'article') return cur;
                                } catch(e) {}
                                cur = cur.parentElement;
                            }
                            return el.parentElement || el;
                        }

                        for (var i=0; i<btns.length; i++){
                            var t = norm(btns[i].innerText || btns[i].textContent);
                            if (!t) continue;
                            if (
                                t.indexOf('phê duyệt') !== -1 || t.indexOf('phe duyet') !== -1 ||
                                t.indexOf('duyệt') !== -1      ||
                                t.indexOf('approve') !== -1    ||
                                t.indexOf('chấp thuận') !== -1 ||
                                t.indexOf('chap thuan') !== -1 ||
                                t.indexOf('từ chối') !== -1    || t.indexOf('tu choi') !== -1 ||
                                t.indexOf('decline') !== -1    || t.indexOf('reject') !== -1
                            ){
                                var root = findRoot(btns[i]);
                                if (!root) continue;
                                // Dùng toạ độ + chiều cao để phân biệt, tránh trùng lặp
                                var r;
                                try { r = root.getBoundingClientRect(); } catch(e) { r = null; }
                                var key = '';
                                if (r) {
                                    key = [Math.round(r.top), Math.round(r.left), Math.round(r.width), Math.round(r.height)].join(':');
                                } else {
                                    key = String(i);
                                }
                                if (!seen.has(key)){
                                    seen.add(key);
                                    roots.push(root);
                                }
                            }
                        }
                        return roots;
                        """
                    ) or []
                except Exception:
                    posts_local = []

            if not posts_local:
                # Nếu tiêu đề báo vẫn còn bài chờ duyệt, thử làm tươi nhẹ rồi quét lại 1 lần
                if pending_count_hint is not None and pending_count_hint > 0:
                    try:
                        self.driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(0.8)
                        self.driver.execute_script("window.scrollBy(0, 600);")
                        time.sleep(0.8)
                        posts_local = self.driver.execute_script(
                            """
                            function norm(s){ return (s||'').toLowerCase(); }
                            var btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                            var roots = [];
                            var seen = new Set();
                            function findRoot(el){
                                var cur = el;
                                for (var i=0; i<10 && cur; i++){
                                    try { if ((cur.getAttribute && cur.getAttribute('role')) === 'article') return cur; } catch(e) {}
                                    cur = cur.parentElement;
                                }
                                return el.parentElement || el;
                            }
                            for (var i=0; i<btns.length; i++){
                                var t = norm(btns[i].innerText || btns[i].textContent);
                                if (!t) continue;
                                if (t.indexOf('phê duyệt')!==-1 || t.indexOf('phe duyet')!==-1 || t.indexOf('approve')!==-1 || t.indexOf('từ chối')!==-1 || t.indexOf('tu choi')!==-1 || t.indexOf('decline')!==-1 || t.indexOf('reject')!==-1){
                                    var root = findRoot(btns[i]);
                                    if (!root) continue;
                                    var r = root.getBoundingClientRect();
                                    var key = [Math.round(r.top), Math.round(r.left), Math.round(r.width), Math.round(r.height)].join(':');
                                    if (!seen.has(key)) { seen.add(key); roots.push(root); }
                                }
                            }
                            return roots;
                            """
                        ) or []
                    except Exception:
                        posts_local = []

            return posts_local

        def _get_post_key(post_el):
            try:
                return self.driver.execute_script(
                    """
                    var art = arguments[0];
                    if (!art) return '';
                    var links = art.querySelectorAll('a[href]');
                    for (var i=0;i<links.length;i++) {
                        var href = links[i].href || '';
                        if (!href) continue;
                        if (href.indexOf('/permalink/') !== -1) return href.split('?')[0];
                        if (href.indexOf('/posts/') !== -1) return href.split('?')[0];
                        if (href.indexOf('story_fbid=') !== -1 && href.indexOf('id=') !== -1) {
                            var m = href.match(/story_fbid=([^&]+)/);
                            var n = href.match(/id=([^&]+)/);
                            if (m && n) return (n[1] + ':' + m[1]);
                        }
                    }
                    if (!art.dataset.fbfixerId) {
                        art.dataset.fbfixerId = 'fbfixer-' + Math.random().toString(36).slice(2);
                    }
                    return art.dataset.fbfixerId || '';
                    """,
                    post_el,
                ) or ""
            except Exception:
                return ""

        processed_total = 0
        approved_total = 0
        rejected_total = 0
        max_rounds = 6
        rounds = 0
        seen_post_keys = set()
        last_scroll_height = 0
        no_growth_rounds = 0

        def _click_action_in_post(post_el, action_name):
            try:
                return bool(self.driver.execute_script(
                    """
                    var root = arguments[0];
                    var action = arguments[1] || '';
                    if (!root) return false;
                    function norm(s){ return (s||'').toLowerCase(); }
                    function textPack(el){
                        if (!el) return '';
                        var t = '';
                        try { t += ' ' + (el.innerText || el.textContent || ''); } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('aria-label') || '')) || ''; } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('data-tooltip-content') || '')) || ''; } catch(e) {}
                        return norm(t);
                    }
                    function matchAction(s){
                        if (!s) return false;
                        if (action === 'approve') {
                            return s.indexOf('phê duyệt') !== -1 || s.indexOf('phe duyet') !== -1 ||
                                   s.indexOf('duyệt') !== -1 || s.indexOf('approve') !== -1 ||
                                   s.indexOf('chấp thuận') !== -1 || s.indexOf('chap thuan') !== -1;
                        }
                        return s.indexOf('từ chối') !== -1 || s.indexOf('tu choi') !== -1 ||
                               s.indexOf('decline') !== -1 || s.indexOf('reject') !== -1;
                    }
                    function clickEl(el){
                        try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
                        try { el.click(); return true; } catch(e) { return false; }
                    }

                    var btns = Array.from(root.querySelectorAll('button, [role="button"]'));
                    for (var i=0;i<btns.length;i++){
                        var txt = textPack(btns[i]);
                        if (matchAction(txt)){
                            if (clickEl(btns[i])) return true;
                        }
                    }

                    // Fallback: look for matching buttons near this post's bounding box
                    var rect = null;
                    try { rect = root.getBoundingClientRect(); } catch(e) { rect = null; }
                    if (!rect) return false;
                    var pad = 18;
                    var candidates = Array.from(document.querySelectorAll('button, [role="button"]'));
                    for (var j=0;j<candidates.length;j++){
                        var t2 = textPack(candidates[j]);
                        if (!matchAction(t2)) continue;
                        var r2 = null;
                        try { r2 = candidates[j].getBoundingClientRect(); } catch(e) { r2 = null; }
                        if (!r2) continue;
                        var inBox = (r2.left >= rect.left - pad && r2.right <= rect.right + pad &&
                                     r2.top >= rect.top - pad && r2.bottom <= rect.bottom + pad);
                        if (inBox){
                            if (clickEl(candidates[j])) return true;
                        }
                    }

                    // Final fallback: pick the closest matching button to the post
                    var best = null;
                    var bestDist = 1e9;
                    var pcx = rect.left + rect.width/2;
                    var pcy = rect.top + rect.height/2;
                    for (var k=0;k<candidates.length;k++){
                        var t3 = textPack(candidates[k]);
                        if (!matchAction(t3)) continue;
                        var r3 = null;
                        try { r3 = candidates[k].getBoundingClientRect(); } catch(e) { r3 = null; }
                        if (!r3) continue;
                        var cx = r3.left + r3.width/2;
                        var cy = r3.top + r3.height/2;
                        var dist = Math.abs(cx - pcx) + Math.abs(cy - pcy);
                        if (dist < bestDist){ bestDist = dist; best = candidates[k]; }
                    }
                    if (best){
                        if (clickEl(best)) return true;
                    }
                    return false;
                    """,
                    post_el,
                    action_name,
                ))
            except Exception:
                return False

        def _click_toolbar_action_near_pending_header(action_name):
            try:
                return bool(self.driver.execute_script(
                    """
                    var action = arguments[0] || '';
                    function norm(s){ return (s||'').toLowerCase(); }
                    function textPack(el){
                        if (!el) return '';
                        var t = '';
                        try { t += ' ' + (el.innerText || el.textContent || ''); } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('aria-label') || '')) || ''; } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('data-tooltip-content') || '')) || ''; } catch(e) {}
                        return norm(t);
                    }
                    function matchAction(s){
                        if (!s) return false;
                        if (action === 'approve') {
                            return s.indexOf('phê duyệt') !== -1 || s.indexOf('phe duyet') !== -1 ||
                                   s.indexOf('duyệt') !== -1 || s.indexOf('approve') !== -1 ||
                                   s.indexOf('chấp thuận') !== -1 || s.indexOf('chap thuan') !== -1;
                        }
                        return s.indexOf('từ chối') !== -1 || s.indexOf('tu choi') !== -1 ||
                               s.indexOf('decline') !== -1 || s.indexOf('reject') !== -1;
                    }
                    function clickEl(el){
                        try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
                        try { el.click(); return true; } catch(e) { return false; }
                    }

                    var headerNodes = Array.from(document.querySelectorAll('h1, h2, h3, span, div'))
                        .filter(function(el){
                            var t = norm(el.innerText || el.textContent || '');
                            return t.indexOf('bài viết đang chờ') !== -1 || t.indexOf('pending posts') !== -1;
                        });
                    if (!headerNodes.length) return false;

                    // Choose the first visible header
                    var header = headerNodes[0];
                    try {
                        header = headerNodes.filter(function(n){
                            var r = n.getBoundingClientRect();
                            return r.width > 50 && r.height > 10;
                        })[0] || headerNodes[0];
                    } catch(e) {}

                    var base = header.closest('div') || header.parentElement;
                    var scope = base || document.body;
                    var btns = Array.from(scope.querySelectorAll('button, [role="button"]'));
                    for (var i=0;i<btns.length;i++){
                        var t = textPack(btns[i]);
                        if (!matchAction(t)) continue;
                        try { if (String(btns[i].getAttribute('aria-disabled')) === 'true') continue; } catch(e) {}
                        if (clickEl(btns[i])) return true;
                    }

                    // Wider fallback: check buttons near the header's y-position
                    try {
                        var hr = header.getBoundingClientRect();
                        var all = Array.from(document.querySelectorAll('button, [role="button"]'));
                        for (var j=0;j<all.length;j++){
                            var r2 = all[j].getBoundingClientRect();
                            if (r2.top < hr.top - 60 || r2.top > hr.bottom + 140) continue;
                            var t2 = textPack(all[j]);
                            if (!matchAction(t2)) continue;
                            try { if (String(all[j].getAttribute('aria-disabled')) === 'true') continue; } catch(e) {}
                            if (clickEl(all[j])) return true;
                        }
                    } catch(e) {}
                    return false;
                    """,
                    action_name,
                ))
            except Exception:
                return False

        def _click_checkbox_then_bulk(post_el, action_name):
            try:
                return bool(self.driver.execute_script(
                    """
                    var post = arguments[0];
                    var action = arguments[1] || '';
                    if (!post) return false;

                    function norm(s){ return (s||'').toLowerCase(); }
                    function textPack(el){
                        if (!el) return '';
                        var t = '';
                        try { t += ' ' + (el.innerText || el.textContent || ''); } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('aria-label') || '')) || ''; } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('data-tooltip-content') || '')) || ''; } catch(e) {}
                        return norm(t);
                    }
                    function matchAction(s){
                        if (!s) return false;
                        if (action === 'approve') {
                            return s.indexOf('phê duyệt') !== -1 || s.indexOf('phe duyet') !== -1 ||
                                   s.indexOf('duyệt') !== -1 || s.indexOf('approve') !== -1 ||
                                   s.indexOf('chấp thuận') !== -1 || s.indexOf('chap thuan') !== -1;
                        }
                        return s.indexOf('từ chối') !== -1 || s.indexOf('tu choi') !== -1 ||
                               s.indexOf('decline') !== -1 || s.indexOf('reject') !== -1;
                    }
                    function clickEl(el){
                        try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
                        try { el.click(); return true; } catch(e) { return false; }
                    }

                    // Find checkbox inside the post
                    var checkbox = post.querySelector('[role="checkbox"], input[type="checkbox"]');
                    if (!checkbox) {
                        // Fallback: find checkbox near post (new layout puts it outside card)
                        var rect = null;
                        try { rect = post.getBoundingClientRect(); } catch(e) { rect = null; }
                        if (rect) {
                            var all = Array.from(document.querySelectorAll('[role="checkbox"], input[type="checkbox"]'));
                            var best = null;
                            var bestDist = 1e9;
                            for (var i=0;i<all.length;i++){
                                var cb = all[i];
                                var r = null;
                                try { r = cb.getBoundingClientRect(); } catch(e) { r = null; }
                                if (!r) continue;
                                var cx = r.left + r.width/2;
                                var cy = r.top + r.height/2;
                                var xOK = (cx >= (rect.left - 120)) && (cx <= (rect.right + 120));
                                var yOK = (cy >= (rect.top - 40)) && (cy <= (rect.bottom + 200));
                                if (!xOK || !yOK) continue;
                                var dist = Math.abs(cx - rect.left) + Math.abs(cy - rect.top);
                                if (dist < bestDist){ bestDist = dist; best = cb; }
                            }
                            if (best) checkbox = best;
                        }
                    }
                    if (checkbox) {
                        var checked = false;
                        try { checked = checkbox.getAttribute('aria-checked') === 'true'; } catch(e) {}
                        if (!checked) {
                            if (!clickEl(checkbox)) {
                                // Try clicking the nearest label/container
                                var label = checkbox.closest('label') || checkbox.parentElement;
                                if (label) clickEl(label);
                            }
                        }
                    } else {
                        return false;
                    }

                    // Click global approve/decline button (toolbar)
                    var btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                    for (var i=0;i<btns.length;i++){
                        var t = textPack(btns[i]);
                        if (matchAction(t)){
                            try {
                                var dis = btns[i].getAttribute('aria-disabled');
                                if (String(dis) === 'true') continue;
                            } catch(e) {}
                            if (clickEl(btns[i])) return true;
                        }
                    }
                    return false;
                    """,
                    post_el,
                    action_name,
                ))
            except Exception:
                return False

        def _click_checkbox_then_bulk_by_element(post_el, action_name):
            try:
                checkbox = self.driver.execute_script(
                    """
                    var post = arguments[0];
                    if (!post) return null;
                    var cb = post.querySelector('[role="checkbox"], input[type="checkbox"]');
                    if (cb) return cb;
                    try {
                        var rect = post.getBoundingClientRect();
                        var all = Array.from(document.querySelectorAll('[role="checkbox"], input[type="checkbox"]'));
                        var best = null;
                        var bestDist = 1e9;
                        for (var i=0;i<all.length;i++){
                            var r = all[i].getBoundingClientRect();
                            var cx = r.left + r.width/2;
                            var cy = r.top + r.height/2;
                            var xOK = (cx >= (rect.left - 120)) && (cx <= (rect.right + 120));
                            var yOK = (cy >= (rect.top - 40)) && (cy <= (rect.bottom + 200));
                            if (!xOK || !yOK) continue;
                            var dist = Math.abs(cx - rect.left) + Math.abs(cy - rect.top);
                            if (dist < bestDist){ bestDist = dist; best = all[i]; }
                        }
                        return best;
                    } catch(e) { return null; }
                    """,
                    post_el,
                )
            except Exception:
                checkbox = None

            if checkbox is None:
                return False

            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).move_to_element(checkbox).click().perform()
                time.sleep(0.4)
            except Exception:
                return False

        def _confirm_post_to_group_dialog():
            try:
                return bool(self.driver.execute_script(
                    """
                    function norm(s){ return (s||'').replace(/\s+/g,' ').trim().toLowerCase(); }
                    function isVisible(el){
                        try {
                            if (!el) return false;
                            var r = el.getBoundingClientRect();
                            if (r.width < 80 || r.height < 60) return false;
                            var st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            return true;
                        } catch(e){ return false; }
                    }
                    var dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(isVisible);
                    for (var i=0;i<dialogs.length;i++){
                        var d = dialogs[i];
                        var t = norm(d.innerText || d.textContent || '');
                        if (!t) continue;
                        if (t.indexOf('đăng lên nhóm') === -1 && t.indexOf('post to group') === -1) continue;
                        var btns = Array.from(d.querySelectorAll('button, [role="button"]'));
                        for (var j=0;j<btns.length;j++){
                            var b = btns[j];
                            var bt = norm(b.innerText || b.textContent || '');
                            var bl = norm(b.getAttribute('aria-label') || '');
                            var label = bt || bl;
                            if (label === 'đăng' || label === 'post') {
                                try { b.click(); return true; } catch(e) {}
                            }
                        }
                    }
                    return false;
                    """
                ))
            except Exception:
                return False

        def _cancel_preapprove_dialog():
            try:
                return bool(self.driver.execute_script(
                    """
                    function norm(s){ return (s||'').replace(/\s+/g,' ').trim().toLowerCase(); }
                    function isVisible(el){
                        try {
                            if (!el) return false;
                            var r = el.getBoundingClientRect();
                            if (r.width < 80 || r.height < 60) return false;
                            var st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            return true;
                        } catch(e){ return false; }
                    }
                    var dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(isVisible);
                    for (var i=0;i<dialogs.length;i++){
                        var d = dialogs[i];
                        var t = norm(d.innerText || d.textContent || '');
                        if (!t) continue;
                        if (t.indexOf('phê duyệt trước') === -1 && t.indexOf('pre-approve') === -1) continue;
                        var btns = Array.from(d.querySelectorAll('button, [role="button"]'));
                        for (var j=0;j<btns.length;j++){
                            var b = btns[j];
                            var bt = norm(b.innerText || b.textContent || '');
                            var bl = norm(b.getAttribute('aria-label') || '');
                            var label = bt || bl;
                            if (label === 'hủy' || label === 'cancel') {
                                try { b.click(); return true; } catch(e) {}
                            }
                        }
                    }
                    return false;
                    """
                ))
            except Exception:
                return False

            try:
                return bool(self.driver.execute_script(
                    """
                    var action = arguments[0] || '';
                    function norm(s){ return (s||'').toLowerCase(); }
                    function textPack(el){
                        if (!el) return '';
                        var t = '';
                        try { t += ' ' + (el.innerText || el.textContent || ''); } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('aria-label') || '')) || ''; } catch(e) {}
                        try { t += ' ' + (el.getAttribute && (el.getAttribute('data-tooltip-content') || '')) || ''; } catch(e) {}
                        return norm(t);
                    }
                    function matchAction(s){
                        if (!s) return false;
                        if (action === 'approve') {
                            return s.indexOf('phê duyệt') !== -1 || s.indexOf('phe duyet') !== -1 ||
                                   s.indexOf('duyệt') !== -1 || s.indexOf('approve') !== -1 ||
                                   s.indexOf('chấp thuận') !== -1 || s.indexOf('chap thuan') !== -1;
                        }
                        return s.indexOf('từ chối') !== -1 || s.indexOf('tu choi') !== -1 ||
                               s.indexOf('decline') !== -1 || s.indexOf('reject') !== -1;
                    }
                    function clickEl(el){
                        try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
                        try { el.click(); return true; } catch(e) { return false; }
                    }
                    var btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                    for (var i=0;i<btns.length;i++){
                        var t = textPack(btns[i]);
                        if (!matchAction(t)) continue;
                        try { if (String(btns[i].getAttribute('aria-disabled')) === 'true') continue; } catch(e) {}
                        if (clickEl(btns[i])) return true;
                    }
                    return false;
                    """,
                    action_name,
                ))
            except Exception:
                return False

        while rounds < max_rounds and not self.approval_stop_event.is_set():
            rounds += 1
            posts = _find_pending_posts()
            if not posts:
                if rounds == 1:
                    self._log("ℹ Không tìm thấy bài chờ duyệt nào (hoặc giao diện khác).", "info")
                break

            processed = 0
            approved = 0
            rejected = 0
            debug_clicked_fail_logged = False

            for post in posts:
                if self.approval_stop_event.is_set():
                    break

                if self._is_action_blocked():
                    self._log("⛔ Facebook đang hạn chế thao tác, dừng duyệt.", "err")
                    break

                try:
                    post_key = _get_post_key(post)
                    if post_key and post_key in seen_post_keys:
                        continue

                    # Lấy text bài viết
                    try:
                        text = self.driver.execute_script(
                            "return (arguments[0].innerText || arguments[0].textContent || '').toLowerCase();",
                            post,
                        )
                    except Exception:
                        text = ""

                    text = text or ""
                    is_suspicious = False
                    for kw in blocked_keywords:
                        if kw and kw in text:
                            is_suspicious = True
                            break

                    action = None  # "approve" | "reject" | None
                    if is_suspicious:
                        action = "reject"
                    elif self.approval_auto_approve_safe.get():
                        action = "approve"

                    if not action:
                        continue

                    # Tìm nút phù hợp bên trong post
                    if action == "approve":
                        clicked = _click_action_in_post(post, "approve")
                        if not clicked:
                            clicked = _click_checkbox_then_bulk(post, "approve")
                        if not clicked:
                            clicked = _click_checkbox_then_bulk_by_element(post, "approve")
                        if not clicked:
                            clicked = _click_toolbar_action_near_pending_header("approve")
                        if clicked:
                            approved += 1
                    else:
                        clicked = _click_action_in_post(post, "reject")
                        if not clicked:
                            clicked = _click_checkbox_then_bulk(post, "reject")
                        if not clicked:
                            clicked = _click_checkbox_then_bulk_by_element(post, "reject")
                        if not clicked:
                            clicked = _click_toolbar_action_near_pending_header("reject")
                        if clicked:
                            rejected += 1

                    if clicked:
                        if post_key:
                            seen_post_keys.add(post_key)
                        processed += 1
                        if action == "approve":
                            try:
                                # Cancel dialog: "Phê duyệt trước bài viết..."
                                for _c in range(2):
                                    if _cancel_preapprove_dialog():
                                        self._log("  ✅ [Duyệt bài] Đã bấm Hủy phê duyệt trước", "info")
                                        break
                                    time.sleep(0.3)
                                # Confirm dialog: "Đăng lên nhóm?"
                                for _c in range(4):
                                    if _confirm_post_to_group_dialog():
                                        self._log("  ✅ [Duyệt bài] Đã xác nhận đăng lên nhóm", "info")
                                        break
                                    time.sleep(0.4)
                            except Exception:
                                pass
                        time.sleep(1.0)
                    else:
                        self._log("  ⚠️ Không click được nút phê duyệt/từ chối (giao diện khác).", "warn")
                        if not debug_clicked_fail_logged:
                            debug_clicked_fail_logged = True
                            try:
                                snap = self.driver.execute_script(
                                    r"""
                                    function norm(s){ return (s||'').toLowerCase(); }
                                    function textPack(el){
                                        if (!el) return '';
                                        var t = '';
                                        try { t += ' ' + (el.innerText || el.textContent || ''); } catch(e) {}
                                        try { t += ' ' + (el.getAttribute && (el.getAttribute('aria-label') || '')) || ''; } catch(e) {}
                                        try { t += ' ' + (el.getAttribute && (el.getAttribute('data-tooltip-content') || '')) || ''; } catch(e) {}
                                        return t.replace(/\s+/g,' ').trim();
                                    }

                                    var checkboxes = Array.from(document.querySelectorAll('[role="checkbox"], input[type="checkbox"]'));
                                    var topButtons = Array.from(document.querySelectorAll('button, [role="button"]'))
                                        .map(textPack)
                                        .filter(function(t){ return t && t.length <= 40; })
                                        .slice(0, 40);

                                    // try to find toolbar-like area near header
                                    var header = document.querySelector('h1, h2, h3');
                                    var nearby = [];
                                    if (header && header.getBoundingClientRect) {
                                        var hr = header.getBoundingClientRect();
                                        var btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                                        for (var i=0;i<btns.length && nearby.length < 20;i++){
                                            var r = btns[i].getBoundingClientRect();
                                            if (r.top >= hr.top - 40 && r.top <= hr.bottom + 120) {
                                                var t = textPack(btns[i]);
                                                if (t) nearby.push(t);
                                            }
                                        }
                                    }

                                    return {
                                        checkboxCount: checkboxes.length,
                                        sampleButtons: topButtons,
                                        nearbyHeaderButtons: nearby
                                    };
                                    """
                                ) or {}
                                self._log(
                                    f"  [dbg] checkbox={snap.get('checkboxCount')} "
                                    f"btns={len(snap.get('sampleButtons') or [])} "
                                    f"nearHeader={snap.get('nearbyHeaderButtons')}",
                                    "debug",
                                )
                            except Exception:
                                pass

                except StaleElementReferenceException:
                    # Bài viết đã bị FB reload / DOM thay đổi khi đang duyệt -> bỏ qua bài này
                    self._log("⚠️ Một bài chờ duyệt đã thay đổi trong khi xử lý (stale element), bỏ qua bài đó.", "warn")
                    continue
                except Exception as e:
                    self._log(f"⚠️ Lỗi khi xử lý một bài chờ duyệt: {e}", "warn")
                    continue

            processed_total += processed
            approved_total += approved
            rejected_total += rejected

            try:
                new_height = int(self.driver.execute_script(
                    "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) || 0;"
                ) or 0)
            except Exception:
                new_height = 0

            if new_height <= (last_scroll_height + 10):
                no_growth_rounds += 1
            else:
                no_growth_rounds = 0
                last_scroll_height = new_height

            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            time.sleep(1.4)

            if processed == 0 and no_growth_rounds >= 2:
                break

        self._log(
            f"✅ [Duyệt bài] Đã xử lý {processed_total} bài (phê duyệt {approved_total}, từ chối {rejected_total}) trong {group_url}",
            "ok",
        )

    # ── Auto đăng bài nhóm ────────────────────────────────────────────────
    def _start_group_posting(self):
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return

        selected = [url for url, data in self.group_post_selected_groups.items() if data['var'].get()]
        if not selected:
            messagebox.showwarning("Chưa chọn nhóm", "Vui lòng chọn ít nhất 1 nhóm để đăng bài!")
            return

        enabled_slots = [s for s in self.group_post_slots if s["enabled"].get()]
        if not enabled_slots:
            messagebox.showwarning("Thiếu nội dung", "Vui lòng bật ít nhất 1 mẫu nội dung để đăng!")
            return

        mode = self.group_post_mode_var.get()
        self.group_post_stop_event.clear()
        self.group_post_schedule_stop_event.clear()
        self._set_run_buttons(self.btn_start_group_post, self.btn_stop_group_post, True, ACCENT, "#e74c3c")
        self._log(f"▶️ [Nhóm] Bắt đầu auto đăng bài ({mode}) cho {len(selected)} nhóm", "info")

        if mode == "schedule":
            self.group_post_last_run_keys.clear()
            self.group_post_schedule_thread = threading.Thread(
                target=self._group_post_schedule_worker, args=(selected,), daemon=True
            )
            self.group_post_schedule_thread.start()
        else:
            self.group_post_thread = threading.Thread(
                target=self._group_post_interval_worker, args=(selected,), daemon=True
            )
            self.group_post_thread.start()

    def _stop_group_posting(self):
        self.group_post_stop_event.set()
        self.group_post_schedule_stop_event.set()
        self._set_run_buttons(self.btn_start_group_post, self.btn_stop_group_post, False, ACCENT, "#e74c3c")
        self._log("⏹ [Nhóm] Đã yêu cầu dừng auto đăng bài", "warn")

    def _get_group_post_templates(self):
        templates = []
        for slot in self.group_post_slots:
            if not slot["enabled"].get():
                continue
            text = ""
            try:
                tw = slot.get("text_widget")
                if tw is not None:
                    text = tw.get("1.0", "end-1c").strip()
            except Exception:
                text = ""
            img = slot.get("image").get().strip() if slot.get("image") else ""
            if text or img:
                templates.append({"text": text, "image": img})
        return templates

    def _get_group_post_daily_counts(self):
        today = dt.datetime.now().strftime("%Y-%m-%d")
        stored = self.group_post_daily_counts or {}
        if stored.get("date") != today:
            self.group_post_daily_counts = {"date": today, "counts": {}}
        if "counts" not in self.group_post_daily_counts:
            self.group_post_daily_counts["counts"] = {}
        return self.group_post_daily_counts["counts"]

    def _group_post_interval_worker(self, group_urls):
        try:
            templates = self._get_group_post_templates()
            if not templates:
                self._log("⚠️ [Nhóm] Không có mẫu nội dung hợp lệ.", "warn")
                return

            tpl_mode = self.group_post_template_mode_var.get()
            tpl_idx = 0
            while not self.group_post_stop_event.is_set():
                session_target = random.randint(
                    max(1, int(self.group_post_session_group_min_var.get() or 1)),
                    max(1, int(self.group_post_session_group_max_var.get() or 1))
                )
                session_done = 0

                for i, group_url in enumerate(group_urls):
                    if self.group_post_stop_event.is_set():
                        break
                    if self._is_action_blocked():
                        self._log("⛔ [Nhóm] Facebook đang hạn chế thao tác, dừng.", "err")
                        self.group_post_stop_event.set()
                        break

                    if self.group_post_skip_pending_var.get():
                        required = self.group_post_pending_required.get(group_url)
                        if required is None:
                            required = self._detect_group_post_requires_approval(group_url)
                            if required is not None:
                                self._set_group_post_pending_required(group_url, required)
                        if required:
                            group_name = self.group_post_selected_groups.get(group_url, {}).get("name", group_url)
                            self._log(f"⏭️ [Nhóm] Bỏ qua nhóm cần kiểm duyệt: {group_name}", "warn")
                            continue

                    counts = self._get_group_post_daily_counts()
                    daily_limit = max(1, int(self.group_post_daily_limit_var.get() or 1))
                    if counts.get(group_url, 0) >= daily_limit:
                        continue

                    if tpl_mode == "random":
                        tpl = random.choice(templates)
                    else:
                        tpl = templates[tpl_idx % len(templates)]
                        tpl_idx += 1

                    group_name = self.group_post_selected_groups.get(group_url, {}).get("name", group_url)
                    self._log(f"🧾 [Nhóm] Đăng bài vào: {group_name}", "info")
                    ok = self._post_to_profile(
                        tpl.get("text"),
                        tpl.get("image"),
                        target_url=group_url,
                        stop_event=self.group_post_stop_event,
                        log_tag="[Nhóm]",
                    )
                    if ok:
                        counts[group_url] = counts.get(group_url, 0) + 1
                        self._log(f"✅ [Nhóm] Đã đăng: {group_name}", "ok")
                    else:
                        self._log(f"⚠️ [Nhóm] Đăng có thể chưa thành công: {group_name}", "warn")

                    session_done += 1
                    if session_done >= session_target and i < (len(group_urls) - 1):
                        rest_min = int(self.group_post_session_rest_min_var.get() or 1)
                        rest_max = int(self.group_post_session_rest_max_var.get() or rest_min)
                        rest = max(1, random.randint(rest_min, rest_max))
                        self._log(f"💤 [Nhóm] Nghỉ giữa phiên {rest} phút...", "info")
                        if self.group_post_stop_event.wait(rest * 60):
                            break
                        session_done = 0
                        session_target = random.randint(
                            max(1, int(self.group_post_session_group_min_var.get() or 1)),
                            max(1, int(self.group_post_session_group_max_var.get() or 1))
                        )

                    rest_min = int(self.group_post_group_rest_min_var.get() or 0)
                    rest_max = int(self.group_post_group_rest_max_var.get() or rest_min)
                    rest = max(0, random.randint(rest_min, rest_max))
                    if rest > 0 and self.group_post_stop_event.wait(rest * 60):
                        break

                if self.group_post_stop_event.is_set():
                    break

                wait_min = max(1, int(self.group_post_interval_min_var.get() or 1))
                wait_max = max(wait_min, int(self.group_post_interval_max_var.get() or wait_min))
                wait_minutes = random.randint(wait_min, wait_max)
                self._log(f"⏳ [Nhóm] Chờ {wait_minutes} phút cho chu kỳ tiếp theo...", "info")
                if self.group_post_stop_event.wait(wait_minutes * 60):
                    break
        finally:
            self._log("🔕 [Nhóm] Đã dừng auto đăng bài", "warn")
            try:
                self.after(0, lambda: self._set_run_buttons(self.btn_start_group_post, self.btn_stop_group_post, False, ACCENT, "#e74c3c"))
            except Exception:
                pass

    def _group_post_schedule_worker(self, group_urls):
        try:
            while not self.group_post_schedule_stop_event.is_set():
                now = dt.datetime.now()
                now_time = now.strftime("%H:%M")
                weekday = now.strftime("%a")

                for idx, slot in enumerate(self.group_post_slots):
                    if self.group_post_schedule_stop_event.is_set():
                        break
                    if not slot["enabled"].get():
                        continue

                    mode = slot["mode"].get()
                    times_raw = (slot["times"].get() or "").strip()
                    times = [t.strip() for t in times_raw.split(",") if t.strip()]
                    if not times:
                        continue

                    if mode == "weekly" and slot["weekday"].get() != weekday:
                        continue

                    for t in times:
                        run_key = f"{idx}:{mode}:{weekday}:{t}:{now.strftime('%Y-%m-%d')}"
                        if run_key in self.group_post_last_run_keys:
                            continue
                        if t != now_time:
                            continue

                        text = ""
                        try:
                            tw = slot.get("text_widget")
                            if tw is not None:
                                text = tw.get("1.0", "end-1c").strip()
                        except Exception:
                            text = ""
                        img = slot.get("image").get().strip() if slot.get("image") else ""
                        if not text and not img:
                            self.group_post_last_run_keys.add(run_key)
                            continue

                        self._log(f"🕒 [Nhóm] Đến giờ đăng mẫu {idx+1} ({mode})", "info")
                        for group_url in group_urls:
                            if self.group_post_schedule_stop_event.is_set():
                                break
                            counts = self._get_group_post_daily_counts()
                            daily_limit = max(1, int(self.group_post_daily_limit_var.get() or 1))
                            if counts.get(group_url, 0) >= daily_limit:
                                continue

                            if self.group_post_skip_pending_var.get():
                                required = self.group_post_pending_required.get(group_url)
                                if required is None:
                                    required = self._detect_group_post_requires_approval(group_url)
                                    if required is not None:
                                        self._set_group_post_pending_required(group_url, required)
                                if required:
                                    group_name = self.group_post_selected_groups.get(group_url, {}).get("name", group_url)
                                    self._log(f"⏭️ [Nhóm] Bỏ qua nhóm cần kiểm duyệt: {group_name}", "warn")
                                    continue

                            group_name = self.group_post_selected_groups.get(group_url, {}).get("name", group_url)
                            self._log(f"🧾 [Nhóm] Đăng bài vào: {group_name}", "info")
                            ok = self._post_to_profile(
                                text,
                                img,
                                target_url=group_url,
                                stop_event=self.group_post_schedule_stop_event,
                                log_tag="[Nhóm]",
                            )
                            if ok:
                                counts[group_url] = counts.get(group_url, 0) + 1
                                self._log(f"✅ [Nhóm] Đã đăng: {group_name}", "ok")
                            else:
                                self._log(f"⚠️ [Nhóm] Đăng có thể chưa thành công: {group_name}", "warn")

                            rest_min = int(self.group_post_group_rest_min_var.get() or 0)
                            rest_max = int(self.group_post_group_rest_max_var.get() or rest_min)
                            rest = max(0, random.randint(rest_min, rest_max))
                            if rest > 0 and self.group_post_schedule_stop_event.wait(rest * 60):
                                break

                        self.group_post_last_run_keys.add(run_key)

                if self.group_post_schedule_stop_event.wait(20):
                    break
        finally:
            self._log("🔕 [Nhóm] Đã dừng auto đăng bài", "warn")
            try:
                self.after(0, lambda: self._set_run_buttons(self.btn_start_group_post, self.btn_stop_group_post, False, ACCENT, "#e74c3c"))
            except Exception:
                pass
    
    def _start_commenting(self):
        """Start commenting on selected groups."""
        if not self.logged_in:
            messagebox.showwarning("Chưa đăng nhập", "Vui lòng đăng nhập Facebook trước!")
            return
        
        selected = [url for url, data in self.selected_groups.items() if data['var'].get()]
        if not selected:
            messagebox.showwarning("Chưa chọn nhóm", "Vui lòng chọn ít nhất 1 nhóm!")
            return

        self._log(f"✅ Đã chọn {len(selected)} nhóm để comment", "info")

        templates = self._get_comment_templates()
        if not templates:
            messagebox.showwarning("Chưa có nội dung", "Vui lòng nhập ít nhất 1 nội dung trong 5 ô mẫu!")
            return

        try:
            self._log(f"🧩 Số đoạn nội dung được nhận: {len(templates)}", "info")
        except Exception:
            pass

        if (not self.comment_old_posts_var.get()) and (not self.monitor_enabled_var.get()):
            messagebox.showwarning(
                "Chưa chọn chế độ chạy",
                "Bạn đã tắt 'Comment bài cũ' và cũng chưa bật monitor bài mới.\n"
                "Hãy bật ít nhất một trong hai.",
            )
            return
        
        self.is_commenting = True
        self.btn_start_comment.configure(state="disabled")
        self._log(f"▶️ Bắt đầu comment {len(selected)} nhóm...", "info")

        # Track total comments across Phase 1 + monitor
        self._comment_session_total = 0
        
        # Clear previous tracking
        self.commented_posts_hash.clear()
        self.commented_posts_uid.clear()
        
        mode = self.comment_mode_var.get()
        # Pass a sample text; actual content is picked per-comment.
        sample_text = templates[0] if templates else ""
        if mode == "sequential":
            threading.Thread(target=self._comment_sequential, args=(selected, sample_text), daemon=True).start()
        else:
            threading.Thread(target=self._comment_parallel, args=(selected, sample_text), daemon=True).start()
    
    def _stop_commenting(self):
        """Stop commenting process."""
        self.is_commenting = False
        self.btn_start_comment.configure(state="normal")
        try:
            total = int(getattr(self, "_comment_session_total", 0) or 0)
        except Exception:
            total = 0
        self._log(f"⏹ Đã dừng (tổng comment: {total})", "warn")
        
        # Stop monitor
        if self.monitor_thread:
            self.monitor_stop_event.set()
            self.monitor_thread = None
    
    def _comment_sequential(self, group_urls, comment_text):
        """Comment on groups sequentially (one by one)."""
        img_path = self.comment_image_path.get().strip()
        post_count = self.comment_post_count.get()
        comment_old = bool(self.comment_old_posts_var.get())
        total_commented = 0
        session_target = self._pick_session_group_limit()
        session_done = 0
        
        # Phase 1: Comment on old posts (optional)
        if comment_old:
            self._log("📝 [Phase 1] Comment bài cũ...", "info")
            for i, group_url in enumerate(group_urls):
                if not self.is_commenting:
                    break

                try:
                    group_name = self.selected_groups[group_url]['name']
                    self._log(f"[{i+1}/{len(group_urls)}] 📝 Comment vào: {group_name}", "info")

                    # Navigate to group
                    self.driver.get(group_url)
                    time.sleep(3)

                    # Comment on old posts (check_duplicates=False for first run)
                    cmt_count = self._comment_on_group_posts(comment_text, img_path, post_count, check_duplicates=False, group_url=group_url)
                    try:
                        total_commented += int(cmt_count or 0)
                        self._comment_session_total += int(cmt_count or 0)
                    except Exception:
                        pass

                    if not self.is_commenting:
                        break

                    self._log(f"✅ Hoàn tất: {group_name}", "ok")
                    session_done += 1

                    if not self._sleep_between_groups():
                        break

                    if session_target and session_done >= session_target and i < (len(group_urls) - 1):
                        if not self._sleep_between_sessions():
                            break
                        session_done = 0
                        session_target = self._pick_session_group_limit()

                except Exception as e:
                    self._log(f"❌ Lỗi ở nhóm {group_url}: {e}", "err")
        else:
            self._log("⏭️ [Phase 1] Bỏ qua comment bài cũ (theo lựa chọn).", "info")

        if not self.is_commenting:
            return

        if comment_old:
            self._log("🎉 [Phase 1] Đã comment xong tất cả bài cũ!", "ok")
        
        # Phase 2: Start monitor mode if enabled
        if self.monitor_enabled_var.get() and self.is_commenting:
            if not comment_old:
                # Nếu chỉ chạy monitor, đánh dấu baseline để không comment các bài đã tồn tại trước đó.
                try:
                    monitor_cap = max(1, int(self.comment_post_count.get() or 1))
                except Exception:
                    monitor_cap = 3
                self._prime_monitor_baseline(group_urls, cap=monitor_cap)
            self._log(f"🔔 [Phase 2] Bắt đầu monitor bài mới...", "info")
            self._start_monitor()
        else:
            # No monitor, stop here
            self.is_commenting = False
            self.btn_start_comment.configure(state="normal")
            try:
                total_all = int(getattr(self, "_comment_session_total", 0) or 0)
            except Exception:
                total_all = total_commented
            self._log(f"✅ Hoàn thành! Tổng cộng đã comment: {total_all}", "ok")
    
    def _comment_parallel(self, group_urls, comment_text):
        """Comment on groups in parallel (multiple tabs)."""
        # Note: This is more complex and can be unstable
        # For now, fallback to sequential
        self._log("⚠️ Chế độ song song chưa hỗ trợ. Dùng tuần tự...", "warn")
        self._comment_sequential(group_urls, comment_text)
    
    def _comment_on_group_posts(self, comment_text, img_path, post_count=3, check_duplicates=True, group_url=None):
        """Find recent posts in current group and comment.
        
        Args:
            check_duplicates: If True, skip posts already commented (for monitor mode)
                            If False, comment all found posts (for initial run)
        """
        try:
            # If Facebook is rate-limiting actions, stop immediately to avoid repeated attempts.
            if self._is_action_blocked():
                self._log("⛔ Facebook đang hạn chế thao tác (spam/rate limit). Dừng để tránh bị chặn thêm.", "err")
                self.is_commenting = False
                try:
                    self._close_all_dialogs(aggressive=True)
                except Exception:
                    pass
                return 0

            # Scroll to load more posts based on post_count
            # Monitor mode should be gentle: minimal scrolling and cap comments
            scroll_times = 1 if check_duplicates else max(2, post_count // 3 + 1)
            if not check_duplicates:
                self._log(f"  📜 Cuộn để tải {post_count} bài...", "info")
            for _ in range(scroll_times):
                if not self.is_commenting:
                    return 0
                self.driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(1.5)
            
            # Find posts - look for article elements or feed posts
            from selenium.webdriver.common.action_chains import ActionChains

            seen_post_ids = set()

            def _collect_unique_posts(post_list):
                unique = []
                for p in post_list:
                    try:
                        pid = self.driver.execute_script(
                            """
                            var art = arguments[0];
                            if (!art) return '';
                            var links = art.querySelectorAll('a[href]');
                            for (var i=0;i<links.length;i++) {
                                var href = links[i].href || '';
                                if (!href) continue;
                                if (href.indexOf('/permalink/') !== -1) return href.split('?')[0];
                                if (href.indexOf('/posts/') !== -1) return href.split('?')[0];
                                if (href.indexOf('story_fbid=') !== -1 && href.indexOf('id=') !== -1) {
                                    var m = href.match(/story_fbid=([^&]+)/);
                                    var n = href.match(/id=([^&]+)/);
                                    if (m && n) return (n[1] + ':' + m[1]);
                                }
                            }
                            // Fallback: hash of visible text snippet
                            var t = (art.innerText || '').trim();
                            return t ? ('txt:' + t.slice(0,120)) : '';
                            """,
                            p,
                        )
                    except Exception:
                        pid = ''

                    if not pid:
                        continue
                    if pid in seen_post_ids:
                        continue
                    seen_post_ids.add(pid)
                    unique.append(p)
                return unique

            posts = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="article"]')
            unique_posts = _collect_unique_posts(posts)
            if unique_posts:
                posts = unique_posts
            
            if not check_duplicates:
                # First run: comment on specified number of posts
                try:
                    posts_to_process = max(1, int(post_count) if post_count else 1)
                except Exception:
                    posts_to_process = 3
                self._log(f"  🔍 Tìm thấy {len(posts)} bài, sẽ comment vào {posts_to_process} bài", "info")
            else:
                # Monitor mode: check all posts for new ones
                # Cap number of NEW comments per group per cycle to avoid spam/blocks
                posts_to_process = max(1, int(post_count) if post_count else 1)
                self._log(f"  🔍 Check {len(posts)} bài tìm bài mới (tối đa {posts_to_process} comment)...", "info")
            
            commented_count = 0
            skipped_count = 0
            skipped_admin = 0
            skipped_already_commented = 0
            skipped_duplicate = 0

            commented_uids_this_run = set()
            scanned_idx = 0
            force_text_only = False
            force_text_only_logged = False
            if group_url and group_url in self.comment_group_text_only:
                force_text_only = True
                img_path = ""
                force_text_only_logged = True
                self._log("  🧷 Nhóm đã ghi nhớ: dùng chữ thuần, bỏ ảnh/số.", "info")

            # Scan posts until we comment enough distinct posts (Phase 1)
            post_index = 0
            extra_scrolls = 0
            max_extra_scrolls = max(10, int(post_count) * 8)
            no_new_rounds = 0
            last_scroll_height = 0

            while self.is_commenting:
                if not self.is_commenting:
                    break

                if self._is_action_blocked():
                    self._log("⛔ Facebook đang hạn chế thao tác. Tự dừng.", "err")
                    self.is_commenting = False
                    try:
                        self._close_all_dialogs(aggressive=True)
                    except Exception:
                        pass
                    break

                if (not check_duplicates) and (commented_count >= posts_to_process):
                    break

                # Monitor mode: stop after reaching cap for this group
                if check_duplicates and (commented_count >= posts_to_process):
                    break

                if post_index >= len(posts):
                    if check_duplicates:
                        break

                    if extra_scrolls >= max_extra_scrolls:
                        if not check_duplicates:
                            self._log("  🛑 Đã cuộn đủ số lần nhưng chưa tìm thêm bài mới.", "info")
                        break

                    # Scroll to load more posts when we still need comments
                    if not check_duplicates:
                        self._log(f"  📜 Cuộn thêm để tìm bài ({extra_scrolls + 1}/{max_extra_scrolls})...", "info")
                    try:
                        last_scroll_height = int(self.driver.execute_script(
                            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) || 0;"
                        ) or 0)
                    except Exception:
                        last_scroll_height = 0

                    # Jump to bottom to force load (more effective than small increments on FB)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2.8)

                    try:
                        new_scroll_height = int(self.driver.execute_script(
                            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) || 0;"
                        ) or 0)
                    except Exception:
                        new_scroll_height = 0

                    if new_scroll_height <= last_scroll_height:
                        # Fallback: small nudge if height didn't change
                        self.driver.execute_script("window.scrollBy(0, 1200);")
                        time.sleep(1.6)
                    extra_scrolls += 1

                    new_posts = _collect_unique_posts(
                        self.driver.find_elements(By.CSS_SELECTOR, 'div[role="article"]')
                    )
                    if new_posts:
                        posts.extend(new_posts)
                        no_new_rounds = 0
                    else:
                        no_new_rounds += 1
                        if no_new_rounds >= 4:
                            if not check_duplicates:
                                self._log("  💤 Cuộn thêm nhưng không thấy bài mới, dừng sớm.", "info")
                            break
                    continue

                try:
                    scanned_idx += 1

                    post = posts[post_index]
                    post_index += 1

                    # Post UID (used to prevent commenting multiple times on the same post)
                    post_uid = ""
                    try:
                        post_uid = self.driver.execute_script(
                            """
                            var art = arguments[0];
                            if (!art) return '';
                            var links = art.querySelectorAll('a[href]');
                            for (var i=0;i<links.length;i++) {
                                var href = links[i].href || '';
                                if (!href) continue;
                                if (href.indexOf('/permalink/') !== -1) return href.split('?')[0];
                                if (href.indexOf('/posts/') !== -1) return href.split('?')[0];
                                if (href.indexOf('story_fbid=') !== -1 && href.indexOf('id=') !== -1) {
                                    var m = href.match(/story_fbid=([^&]+)/);
                                    var n = href.match(/id=([^&]+)/);
                                    if (m && n) return (n[1] + ':' + m[1]);
                                }
                            }
                            var t = (art.innerText || '').trim();
                            return t ? ('txt:' + t.slice(0,120)) : '';
                            """,
                            post,
                        ) or ""
                    except Exception:
                        post_uid = ""

                    if post_uid and (post_uid in commented_uids_this_run):
                        skipped_count += 1
                        continue

                    # Skip if we've already commented this post earlier in this run/session (reliable in monitor mode)
                    # Only trust stable UIDs (permalink/posts/story id). The text fallback (txt:...) can collide.
                    if post_uid and (not post_uid.startswith('txt:')) and (post_uid in self.commented_posts_uid):
                        skipped_count += 1
                        skipped_duplicate += 1
                        continue
                    
                    # Get post text for duplicate checking
                    post_text = ""
                    try:
                        # Find text content in post
                        text_elements = post.find_elements(By.CSS_SELECTOR, '[dir="auto"]')
                        for elem in text_elements:
                            txt = elem.text.strip()
                            if txt and len(txt) > 20:  # Reasonable post text
                                post_text = txt[:200]  # First 200 chars for hash
                                break
                    except:
                        pass
                    
                    # Check if already commented (only in monitor mode)
                    if check_duplicates and post_text:
                        post_hash = hash(post_text)
                        if post_hash in self.commented_posts_hash:
                            skipped_count += 1
                            skipped_duplicate += 1
                            continue  # Skip this post
                    
                    # Scroll post into view
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
                    time.sleep(0.5)
                    
                    # 🚫 Skip if post is from Admin/Moderator
                    is_admin_post = False
                    try:
                        # Method 1: Look for admin/moderator badges/text in the post header
                        admin_patterns = [
                            'Admin', 'admin', 'ADMIN',
                            'Quản trị viên', 'quản trị viên',
                            'Moderator', 'moderator', 'MODERATOR',
                            'Người kiểm duyệt', 'người kiểm duyệt',
                            'Group Admin', 'Group admin'
                        ]
                        
                        post_html = post.get_attribute('innerHTML')
                        for pattern in admin_patterns:
                            if pattern in post_html:
                                # Double check it's in the author section, not just post content
                                author_elements = post.find_elements(By.XPATH,
                                    ".//*[contains(@class, 'author') or contains(@aria-label, 'author')]")
                                
                                for elem in author_elements:
                                    if pattern in elem.text or pattern in elem.get_attribute('innerHTML'):
                                        is_admin_post = True
                                        break
                                
                                if not is_admin_post:
                                    # Fallback: check near the top of post (first 500 chars of HTML)
                                    if pattern in post_html[:500]:
                                        is_admin_post = True
                                        break
                        
                        if is_admin_post:
                            if not check_duplicates:
                                self._log(f"  ⏭️ [{scanned_idx}] Skip: Bài của Admin/Moderator", "info")
                            skipped_count += 1
                            skipped_admin += 1
                            continue
                    except Exception as e:
                        # Fail silently, continue to next check
                        pass
                    
                    # 🚫 Skip if already commented by current user
                    already_commented = False
                    try:
                        # Method 1: Use JavaScript to check for existing comments more reliably
                        check_commented_js = """
                        var post = arguments[0];
                        var indicators = [
                            'Bạn đã bình luận',
                            'You commented',
                            'Your comment',
                            'Bình luận của bạn'
                        ];
                        
                        // Check if any text in post contains these indicators
                        var postText = post.innerText || post.textContent;
                        for (var i = 0; i < indicators.length; i++) {
                            if (postText.includes(indicators[i])) {
                                return true;
                            }
                        }
                        
                        // Check for comment-specific edit/delete actions (avoid matching post/menu actions)
                        var editButtons = post.querySelectorAll(
                            '[aria-label*="Edit comment" i], [aria-label*="Chỉnh sửa bình luận" i]'
                        );
                        var deleteButtons = post.querySelectorAll(
                            '[aria-label*="Delete comment" i], [aria-label*="Xóa bình luận" i], [aria-label*="Gỡ bình luận" i]'
                        );

                        if (editButtons.length > 0 || deleteButtons.length > 0) return true;
                        
                        return false;
                        """
                        
                        already_commented = self.driver.execute_script(check_commented_js, post)
                        
                        # Method 2: Fallback - check for "See your comment" link or similar
                        if not already_commented:
                            comment_links = post.find_elements(By.XPATH,
                                ".//*[contains(@aria-label, 'comment') and "
                                "(contains(@aria-label, 'your') or contains(@aria-label, 'Của bạn'))]")
                            if comment_links:
                                already_commented = True
                        
                        if already_commented:
                            if not check_duplicates:
                                self._log(f"  ⏭️ [{scanned_idx}] Skip: Đã comment rồi", "info")
                            skipped_count += 1
                            skipped_already_commented += 1
                            continue
                            
                    except Exception as e:
                        # Fail silently, continue to comment
                        pass
                    
                    # Find comment box in this post.
                    # IMPORTANT: Facebook often renders the comment composer only after clicking the "Bình luận/Comment" button.
                    comment_elements = []

                    def _pick_comment_boxes(scope_el):
                        boxes = []
                        try:
                            candidates = scope_el.find_elements(
                                By.CSS_SELECTOR,
                                '[role="textbox"][contenteditable="true"], '
                                '[role="textbox"][contenteditable="plaintext-only"], '
                                '[contenteditable="true"][data-lexical-editor="true"], '
                                '[contenteditable="plaintext-only"][data-lexical-editor="true"], '
                                '[contenteditable="true"], [contenteditable="plaintext-only"]'
                            )
                            for elem in candidates:
                                try:
                                    ce = (elem.get_attribute('contenteditable') or '').lower()
                                    if ce == 'false':
                                        continue
                                    aria = (elem.get_attribute('aria-label') or "").lower()
                                    menu_keywords = [
                                        'ẩn hoặc báo cáo', 'gỡ bình luận', 'hide or report',
                                        'remove comment', 'xóa bình luận', 'chặn', 'block'
                                    ]
                                    if any(k in aria for k in menu_keywords):
                                        continue

                                    rect = self.driver.execute_script(
                                        "var r=arguments[0].getBoundingClientRect(); return {w:r.width,h:r.height};",
                                        elem,
                                    )
                                    if isinstance(rect, dict):
                                        if rect.get('w', 0) < 200 or rect.get('h', 0) < 18:
                                            continue
                                    boxes.append(elem)
                                except Exception:
                                    boxes.append(elem)
                        except Exception:
                            pass

                        if not boxes:
                            return []

                        # Prefer elements that explicitly look like comment boxes
                        priority = []
                        for b in boxes:
                            try:
                                a = (b.get_attribute('aria-label') or '').lower()
                                if (
                                    ('comment' in a) or ('bình luận' in a) or ('viết' in a) or ('write' in a)
                                    or ('dưới tên' in a) or ('public comment' in a)
                                ):
                                    priority.append(b)
                            except Exception:
                                continue
                        return priority or boxes

                    # Use the closest article container to reduce false positives
                    post_scope = post
                    try:
                        post_scope = post.find_element(By.XPATH, './/ancestor-or-self::*[@role="article"][1]')
                    except Exception:
                        pass

                    comment_elements = _pick_comment_boxes(post_scope)

                    # Retry: click "Bình luận/Comment" and wait longer before searching again
                    if not comment_elements:
                        for _retry in range(2):
                            try:
                                comment_btns = post_scope.find_elements(
                                    By.XPATH,
                                    "(.//*[@role='button' or @role='link'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'bình luận') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'comment')])[1]"
                                )
                                if comment_btns:
                                    self.driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                                        comment_btns[0],
                                    )
                                    time.sleep(1.6)
                            except Exception:
                                pass

                            comment_elements = _pick_comment_boxes(post_scope)
                            if comment_elements:
                                break

                    # If not found, click the Comment button to open the composer, then search again
                    if not comment_elements:
                        try:
                            clicked_btn = None
                            target_point = None
                            try:
                                target_point = self.driver.execute_script(
                                    "var r=arguments[0].getBoundingClientRect(); return {x:r.left + r.width/2, y:r.top + r.height/2};",
                                    post_scope,
                                )
                            except Exception:
                                target_point = None

                            # 1) XPath attempt (text-based)
                            comment_btns = post_scope.find_elements(
                                By.XPATH,
                                "(.//*[@role='button' or @role='link'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'bình luận') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'comment')])[1]"
                            )
                            if comment_btns:
                                clicked_btn = comment_btns[0]
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                                    comment_btns[0],
                                )
                                time.sleep(1.0)
                                comment_elements = _pick_comment_boxes(post_scope)

                            # 2) JS fallback: click a button whose innerText is 'Bình luận'/'Comment'
                            if not comment_elements:
                                clicked = self.driver.execute_script(
                                    """
                                    var root = arguments[0];
                                    if (!root) return false;
                                    var btns = root.querySelectorAll('[role="button"], [role="link"]');
                                    for (var i=0;i<btns.length;i++) {
                                        var t = (btns[i].innerText || btns[i].textContent || '').trim().toLowerCase();
                                        if (t === 'bình luận' || t === 'comment') {
                                            btns[i].scrollIntoView({block:'center'});
                                            btns[i].click();
                                            return true;
                                        }
                                    }
                                    return false;
                                    """,
                                    post_scope,
                                )
                                if clicked:
                                    time.sleep(1.0)
                                    comment_elements = _pick_comment_boxes(post_scope)

                            # 3) If still not found, the editor may be rendered outside the post (portal).
                            #    Grab focused editor (document.activeElement) or nearest visible editor on page.
                            if not comment_elements:
                                editor = self.driver.execute_script(
                                    """
                                    function closestEditable(el) {
                                        if (!el) return null;
                                        if (el.getAttribute && el.getAttribute('contenteditable') && el.getAttribute('contenteditable') !== 'false') return el;
                                        if (el.closest) {
                                            var c = el.closest('[contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"]');
                                            if (c && c.getAttribute('contenteditable') !== 'false') return c;
                                        }
                                        return null;
                                    }

                                    function centerOf(el) {
                                        try {
                                            var r = el.getBoundingClientRect();
                                            return {x: r.left + r.width/2, y: r.top + r.height/2, w:r.width, h:r.height};
                                        } catch(e) {
                                            return null;
                                        }
                                    }

                                    var btn = arguments[0] || null;
                                    var tp = arguments[1] || null;
                                    var postEl = arguments[2] || null;

                                    function postRect() {
                                        try {
                                            if (!postEl || !postEl.getBoundingClientRect) return null;
                                            return postEl.getBoundingClientRect();
                                        } catch(e) { return null; }
                                    }

                                    function withinPost(el) {
                                        try {
                                            var pr = postRect();
                                            if (!pr) return true; // if we can't compute, don't block
                                            var r = el.getBoundingClientRect();
                                            var cx = r.left + r.width/2;
                                            var cy = r.top + r.height/2;
                                            // allow a little horizontal/vertical margin; allow editors slightly below the card
                                            var xOK = (cx >= (pr.left - 40)) && (cx <= (pr.right + 40));
                                            var yOK = (cy >= (pr.top - 60)) && (cy <= (pr.bottom + 300));
                                            return xOK && yOK;
                                        } catch(e) { return true; }
                                    }

                                    // Determine target point
                                    var targetX = window.innerWidth / 2;
                                    var targetY = window.innerHeight / 2;
                                    if (tp && typeof tp.x === 'number' && typeof tp.y === 'number') {
                                        targetX = tp.x;
                                        targetY = tp.y;
                                    }
                                    if (btn && btn.getBoundingClientRect) {
                                        var br = btn.getBoundingClientRect();
                                        targetY = br.top + 40;
                                        targetX = br.left + (br.width / 2);
                                    }

                                    var ae = document.activeElement;
                                    var focused = closestEditable(ae);
                                    if (focused) {
                                        var fc = centerOf(focused);
                                        if (fc) {
                                            var fdist = Math.abs(fc.x - targetX) + Math.abs(fc.y - targetY);
                                            // Only accept focused editor if it's close to the current post
                                            if (fdist < 520 && withinPost(focused)) return focused;
                                        }
                                    }

                                    // Otherwise, pick the nearest visible editable near the clicked button or viewport center
                                    var cands = Array.from(document.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"][contenteditable]'));
                                    if (!cands.length) return null;

                                    function pickBest(list) {
                                        var best = null;
                                        var bestScore = 1e18;
                                        for (var i=0;i<list.length;i++) {
                                            var el = list[i];
                                            var ce = (el.getAttribute('contenteditable') || '').toLowerCase();
                                            if (ce === 'false') continue;
                                            var r = el.getBoundingClientRect();
                                            if (r.width < 200 || r.height < 18) continue;
                                            if (r.bottom < 0 || r.top > window.innerHeight) continue;
                                            var dx = Math.abs((r.left + r.width/2) - targetX);
                                            var dy = Math.abs((r.top + r.height/2) - targetY);
                                            var score = dx + dy;
                                            if (score < bestScore) {
                                                bestScore = score;
                                                best = el;
                                            }
                                        }
                                        return best;
                                    }

                                    // First try: only editors within the current post's card
                                    var inPost = cands.filter(function(el){ return withinPost(el); });
                                    var bestInPost = pickBest(inPost);
                                    if (bestInPost) return bestInPost;

                                    // Fallback: any visible editor
                                    return pickBest(cands);
                                    """,
                                    clicked_btn,
                                    target_point,
                                    post_scope,
                                )
                                if editor:
                                    comment_elements = [editor]
                        except Exception:
                            pass

                    # Debug info when not found (helps tune selectors without spamming monitor mode)
                    if (not comment_elements) and (not check_duplicates):
                        try:
                            dbg = self.driver.execute_script(
                                """
                                var root = arguments[0];
                                if (!root) return {count:0, labels:[]};
                                var els = root.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"]');
                                var labels = [];
                                for (var i=0;i<els.length;i++) {
                                    var a = (els[i].getAttribute('aria-label') || '').trim();
                                    if (a && labels.indexOf(a) === -1) labels.push(a);
                                    if (labels.length >= 3) break;
                                }
                                return {count: els.length, labels: labels};
                                """,
                                post_scope,
                            )
                            if isinstance(dbg, dict):
                                self._log(f"  🔎 Debug: contenteditable={dbg.get('count',0)} labels={dbg.get('labels',[])}", "info")
                        except Exception:
                            pass
                    
                    if comment_elements:
                        comment_success = False
                        retry_text_only = False
                        rejected_reason = ""
                        
                        # Try to click and comment with retry mechanism
                        for attempt in range(4):  # extra attempt for text-only retry
                            try:
                                if not self.is_commenting:
                                    break

                                if self._is_action_blocked():
                                    self._log("⛔ Facebook đang hạn chế thao tác. Tự dừng.", "err")
                                    self.is_commenting = False
                                    try:
                                        self._close_all_dialogs(aggressive=True)
                                    except Exception:
                                        pass
                                    break

                                # Ensure element is visible
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                                    comment_elements[0]
                                )
                                time.sleep(0.5)
                                
                                # Attempt 1, 2: Try closing overlays first
                                if attempt > 0:
                                    try:
                                        self.driver.execute_script("""
                                            // Close tooltips, notifications, overlays
                                            document.querySelectorAll('[role="tooltip"], [role="dialog"]').forEach(function(el) {
                                                if (el.style.position === 'fixed' || el.style.position === 'absolute') {
                                                    try { el.style.display = 'none'; } catch(e) {}
                                                }
                                            });
                                        """)
                                        time.sleep(0.3)
                                    except:
                                        pass
                                
                                # JavaScript click (bypass overlay issues)
                                self.driver.execute_script("arguments[0].click();", comment_elements[0])
                                time.sleep(0.8)

                                # Resolve the actual editable element (Facebook often nests it)
                                textarea_el = comment_elements[0]
                                try:
                                    ce = (textarea_el.get_attribute('contenteditable') or '').lower()
                                    if ce in ['', 'false']:
                                        textarea_el = comment_elements[0].find_element(
                                            By.CSS_SELECTOR,
                                            '[contenteditable="true"], [contenteditable="plaintext-only"], [role="textbox"][contenteditable]'
                                        )
                                except Exception:
                                    pass

                                # Focus + clear existing
                                try:
                                    self.driver.execute_script("arguments[0].focus();", textarea_el)
                                except Exception:
                                    pass
                                try:
                                    textarea_el.click()
                                except Exception:
                                    pass

                                try:
                                    textarea_el.send_keys(Keys.CONTROL + "a")
                                    textarea_el.send_keys(Keys.BACKSPACE)
                                except Exception:
                                    pass

                                # Type text: paste multi-line as a single block to avoid per-line submit.
                                comment_text = self._build_comment_text()
                                if not comment_text:
                                    raise Exception("Empty comment text")

                                if retry_text_only or force_text_only:
                                    comment_text = self._sanitize_text_for_pending(comment_text)
                                    if not comment_text:
                                        raise Exception("Empty text after removing links")

                                pasted_ok = False
                                try:
                                    import subprocess

                                    def _set_clipboard(txt):
                                        try:
                                            process = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE, shell=True)
                                            process.communicate(txt.encode('utf-16-le'))
                                        except Exception:
                                            try:
                                                import tkinter as _tk
                                                _r = _tk.Tk()
                                                _r.withdraw()
                                                _r.clipboard_clear()
                                                _r.clipboard_append(txt)
                                                _r.update()
                                                _r.destroy()
                                            except Exception:
                                                pass

                                    _set_clipboard(comment_text)
                                    actions = ActionChains(self.driver)
                                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                                    time.sleep(0.4)
                                    try:
                                        current_val = (textarea_el.text or '').strip()
                                    except Exception:
                                        current_val = ''
                                    if current_val:
                                        pasted_ok = True
                                except Exception:
                                    pasted_ok = False

                                if not pasted_ok:
                                    try:
                                        _ = self.driver.execute_script(
                                            """
                                            var el = arguments[0];
                                            var text = arguments[1];
                                            if (!el) return false;
                                            el.focus();
                                            try {
                                                var sel = window.getSelection();
                                                if (sel && sel.removeAllRanges) {
                                                    sel.removeAllRanges();
                                                    var r = document.createRange();
                                                    r.selectNodeContents(el);
                                                    r.collapse(false);
                                                    sel.addRange(r);
                                                }
                                            } catch(e) {}
                                            var ok = false;
                                            try { ok = document.execCommand('insertText', false, text); } catch(e2) {}
                                            try {
                                                var ev = new InputEvent('input', {bubbles:true, inputType:'insertText', data:text});
                                                el.dispatchEvent(ev);
                                            } catch(e3) {
                                                try { el.dispatchEvent(new Event('input', {bubbles:true})); } catch(e4) {}
                                            }
                                            return ok;
                                            """,
                                            textarea_el,
                                            comment_text,
                                        )
                                    except Exception:
                                        pass

                                    try:
                                        current_val = (textarea_el.text or '').strip()
                                    except Exception:
                                        current_val = ''

                                    if (not current_val) or (len(current_val) < 2):
                                        # Last fallback: send lines with Shift+Enter between them.
                                        lines = comment_text.splitlines() or [comment_text]
                                        for li, line in enumerate(lines):
                                            if line:
                                                textarea_el.send_keys(line)
                                            if li < len(lines) - 1:
                                                actions = ActionChains(self.driver)
                                                actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()

                                time.sleep(0.6)

                                # Attach image if provided
                                if retry_text_only or force_text_only:
                                    img_choice = ""
                                else:
                                    pool = self._get_comment_images()
                                    if pool:
                                        img_choice = random.choice(pool)
                                    else:
                                        img_choice = img_path
                                if img_choice and os.path.isfile(img_choice):
                                    try:
                                        file_input = None
                                        # Prefer file input near the editor
                                        try:
                                            file_input = self.driver.execute_script(
                                                """
                                                var el = arguments[0];
                                                function pick(root) {
                                                    if (!root) return null;
                                                    var inputs = root.querySelectorAll('input[type="file"]');
                                                    for (var i=0;i<inputs.length;i++) {
                                                        return inputs[i];
                                                    }
                                                    return null;
                                                }
                                                // climb up
                                                var cur = el;
                                                for (var d=0; d<8 && cur; d++) {
                                                    var got = pick(cur);
                                                    if (got) return got;
                                                    cur = cur.parentElement;
                                                }
                                                // fallback global nearest
                                                var all = Array.from(document.querySelectorAll('input[type="file"]'));
                                                if (!all.length) return null;
                                                var r = el.getBoundingClientRect();
                                                var tx = r.left + r.width/2;
                                                var ty = r.top + r.height/2;
                                                var best=null, bestScore=1e18;
                                                for (var j=0;j<all.length;j++) {
                                                    var rr = all[j].getBoundingClientRect();
                                                    var dx = Math.abs((rr.left+rr.width/2)-tx);
                                                    var dy = Math.abs((rr.top+rr.height/2)-ty);
                                                    var sc = dx+dy;
                                                    if (sc < bestScore) { bestScore=sc; best=all[j]; }
                                                }
                                                return best;
                                                """,
                                                textarea_el,
                                            )
                                        except Exception:
                                            file_input = None

                                        if file_input:
                                            try:
                                                file_input.send_keys(img_choice)
                                                # Wait a bit for upload/render
                                                for _w in range(14):
                                                    time.sleep(0.5)
                                                    busy = self.driver.execute_script(
                                                        """
                                                        var root = document;
                                                        // crude check: any progressbar/dialog that indicates upload
                                                        var p = root.querySelector('[role="progressbar"], [aria-label*="Đang tải" i], [aria-label*="Uploading" i]');
                                                        return !!p;
                                                        """
                                                    )
                                                    if not busy:
                                                        break
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                # Submit with a real Enter key
                                if not self.is_commenting:
                                    break
                                if self._is_action_blocked():
                                    self._log("⛔ Facebook đang hạn chế thao tác. Tự dừng.", "err")
                                    self.is_commenting = False
                                    break
                                try:
                                    textarea_el.send_keys(Keys.ENTER)
                                except Exception:
                                    actions = ActionChains(self.driver)
                                    actions.send_keys(Keys.ENTER)
                                    actions.perform()

                                # Verify submission: editor usually clears shortly after posting
                                submitted = False
                                for _ in range(6):
                                    if not self.is_commenting:
                                        break
                                    if self._is_action_blocked():
                                        self._log("⛔ Facebook đang hạn chế thao tác. Tự dừng.", "err")
                                        self.is_commenting = False
                                        break
                                    time.sleep(0.5)
                                    try:
                                        after_val = (textarea_el.text or '').strip()
                                    except Exception:
                                        after_val = ''
                                    if not after_val:
                                        submitted = True
                                        break

                                if not submitted:
                                    raise Exception("Comment may not have been submitted")

                                # Detect auto-rejected or pending comment (may render a bit later)
                                pending_reason = ""
                                for _ in range(12):
                                    time.sleep(0.6)
                                    rejected_reason = self._detect_rejected_comment(post)
                                    if rejected_reason:
                                        break
                                    pending_reason = self._detect_pending_comment(post)
                                    if pending_reason:
                                        break

                                if rejected_reason:
                                    if not retry_text_only:
                                        self._log("  ⚠️ Bình luận bị từ chối, thử lại bằng chữ thuần...", "warn")
                                        retry_text_only = True
                                        comment_success = False
                                        continue
                                    self._log("  ⛔ Bình luận chữ thuần vẫn bị từ chối, bỏ qua bài này.", "warn")
                                    comment_success = False
                                    break

                                if pending_reason and not force_text_only:
                                    self._log("  ⚠️ Comment đang chờ duyệt → chuyển sang chữ thuần, bỏ ảnh/số.", "warn")
                                    force_text_only = True
                                    img_path = ""
                                    if not force_text_only_logged:
                                        force_text_only_logged = True
                                    if group_url:
                                        if group_url not in self.comment_group_text_only:
                                            self.comment_group_text_only.add(group_url)
                                            self._log("  🧷 Ghi nhớ nhóm: luôn dùng chữ thuần, bỏ ảnh/số.", "info")

                                comment_success = True
                                break  # Success, exit retry loop
                                
                            except Exception as click_err:
                                if attempt == 2:  # Last attempt
                                    if not check_duplicates:
                                        # Shortened error message
                                        err_msg = str(click_err).split('\n')[0][:80]
                                        self._log(f"  ❌ [{scanned_idx}] Lỗi: {err_msg}", "err")
                                # Continue to next attempt
                        
                        if comment_success:
                            # Mark as commented
                            if post_text:
                                self.commented_posts_hash.add(hash(post_text))

                            if post_uid and (not post_uid.startswith('txt:')):
                                commented_uids_this_run.add(post_uid)
                                self.commented_posts_uid.add(post_uid)
                            
                            commented_count += 1
                            if not check_duplicates:
                                self._log(f"  ✅ [{commented_count}/{posts_to_process}] Đã comment", "ok")
                            else:
                                self._log(f"  ✅ Đã comment bài mới", "ok")

                            if self.is_commenting:
                                try:
                                    min_s = int(self.comment_delay_min_var.get())
                                    max_s = int(self.comment_delay_max_var.get())
                                except Exception:
                                    min_s, max_s = 10, 20
                                if min_s < 0:
                                    min_s = 0
                                if max_s < min_s:
                                    max_s = min_s
                                pause_seconds = random.randint(min_s, max_s) if max_s > 0 else 0
                                if pause_seconds > 0:
                                    if not check_duplicates:
                                        self._log(f"  ⏳ Nghỉ {pause_seconds}s trước comment tiếp theo...", "info")
                                    time.sleep(pause_seconds)
                    else:
                        if not check_duplicates:
                            self._log(f"  ⚠️ [{scanned_idx}] Không tìm thấy comment box", "warn")
                        
                except Exception as e:
                    if not check_duplicates:
                        self._log(f"  ❌ [{scanned_idx}] Lỗi: {e}", "err")
                    continue
            
            if not check_duplicates:
                # First run summary
                summary_parts = [f"🎉 Đã comment {commented_count}/{posts_to_process} bài"]
                if skipped_admin > 0:
                    summary_parts.append(f"skip {skipped_admin} admin")
                if skipped_already_commented > 0:
                    summary_parts.append(f"skip {skipped_already_commented} đã comment")
                
                if commented_count > 0:
                    self._log(f"  {' | '.join(summary_parts)}", "ok")
                else:
                    self._log(f"  ⚠️ Không comment được bài nào (skip: {skipped_count})", "warn")
            else:
                # Monitor mode summary
                if commented_count > 0:
                    summary_parts = [f"🎉 Comment {commented_count} bài mới"]
                    if skipped_duplicate > 0:
                        summary_parts.append(f"skip {skipped_duplicate} bài cũ")
                    if skipped_admin > 0:
                        summary_parts.append(f"skip {skipped_admin} admin")
                    if skipped_already_commented > 0:
                        summary_parts.append(f"skip {skipped_already_commented} đã comment")
                    self._log(f"  {' | '.join(summary_parts)}", "ok")
                else:
                    self._log(f"  💤 Không có bài mới (skip: {skipped_count})", "info")
                
        except Exception as e:
            self._log(f"  ❌ Lỗi khi comment: {e}", "err")
        return commented_count

    def _get_comment_templates(self):
        templates = []
        for box in (self.comment_textboxes or []):
            try:
                txt = box.get("1.0", "end-1c").strip()
            except Exception:
                txt = ""
            if txt:
                templates.append(txt)
        return templates

    def _sleep_interruptible(self, seconds):
        try:
            total = float(seconds)
        except Exception:
            total = 0
        if total <= 0:
            return True
        end = time.time() + total
        while time.time() < end:
            if not self.is_commenting:
                return False
            time.sleep(0.5)
        return True

    def _pick_session_group_limit(self):
        try:
            min_g = int(self.comment_session_group_min_var.get())
            max_g = int(self.comment_session_group_max_var.get())
        except Exception:
            min_g, max_g = 10, 20
        if min_g <= 0 and max_g <= 0:
            return 0
        if min_g < 1:
            min_g = 1
        if max_g < min_g:
            max_g = min_g
        return random.randint(min_g, max_g)

    def _sleep_between_groups(self):
        try:
            min_m = int(self.comment_group_rest_min_var.get())
            max_m = int(self.comment_group_rest_max_var.get())
        except Exception:
            min_m, max_m = 2, 5
        if min_m < 0:
            min_m = 0
        if max_m < min_m:
            max_m = min_m
        if max_m == 0:
            return True
        pause_min = random.randint(min_m, max_m)
        if pause_min > 0:
            self._log(f"  ⏳ Nghỉ {pause_min} phút trước nhóm tiếp theo...", "info")
            return self._sleep_interruptible(pause_min * 60)
        return True

    def _sleep_between_sessions(self):
        try:
            min_m = int(self.comment_session_rest_min_var.get())
            max_m = int(self.comment_session_rest_max_var.get())
        except Exception:
            min_m, max_m = 30, 60
        if min_m < 0:
            min_m = 0
        if max_m < min_m:
            max_m = min_m
        pause_min = random.randint(min_m, max_m) if max_m > 0 else 0
        if pause_min > 0:
            self._log(f"🧘 Nghỉ {pause_min} phút giữa phiên để giảm rủi ro hạn chế...", "warn")
            return self._sleep_interruptible(pause_min * 60)
        return True

    def _build_comment_text(self):
        templates = self._get_comment_templates()
        if not templates:
            return ""
        base = random.choice(templates).strip()
        if not base:
            return ""
        if not self.comment_use_variation_var.get():
            return base
        suffixes = ["", ".", "!", "!!", "..."]
        suffix = random.choice(suffixes)
        if suffix and base.endswith((".", "!", "?")):
            suffix = ""
        return f"{base}{suffix}"

    def _get_comment_images(self):
        if self.comment_images_box is None:
            return []
        raw = self.comment_images_box.get("1.0", "end-1c")
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        return [p for p in items if os.path.isfile(p)]

    def _pick_comment_image(self):
        pool = self._get_comment_images()
        if pool:
            return random.choice(pool)
        img = self.comment_image_path.get().strip()
        if img and os.path.isfile(img):
            return img
        return ""
    
    def _start_monitor(self):
        """Start monitoring for new posts."""
        if self.monitor_thread:
            return
        
        self._log("🔔 Bắt đầu monitor mode...", "info")
        self.monitor_stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self.monitor_thread.start()

    def _prime_monitor_baseline(self, group_urls, cap=3):
        """Đánh dấu các bài hiện có là 'đã thấy' để monitor chỉ comment bài mới về sau."""
        try:
            cap = max(1, int(cap or 1))
        except Exception:
            cap = 3

        self._log(f"🧭 [Monitor] Đang lấy mốc ban đầu ({cap} bài gần nhất/nhóm)...", "info")

        seeded = 0
        for idx, group_url in enumerate(group_urls):
            if not self.is_commenting:
                break
            try:
                group_name = self.selected_groups.get(group_url, {}).get('name', group_url)
                self._log(f"  🧭 [{idx+1}/{len(group_urls)}] Ghi nhận bài hiện có: {group_name}", "info")
                self.driver.get(group_url)
                time.sleep(2)

                uids = self.driver.execute_script(
                    r"""
                    var cap = Math.max(1, parseInt(arguments[0] || 3, 10));
                    var out = [];
                    var seen = new Set();

                    function pushUid(v){
                        if (!v) return;
                        if (seen.has(v)) return;
                        seen.add(v);
                        out.push(v);
                    }

                    var articles = Array.from(document.querySelectorAll('div[role="article"]'));
                    for (var i=0; i<articles.length && out.length < cap; i++) {
                        var art = articles[i];
                        var links = Array.from(art.querySelectorAll('a[href*="/posts/"], a[href*="story_fbid="], a[href*="permalink"], a[href*="/groups/"]'));
                        var uid = null;
                        for (var j=0; j<links.length; j++) {
                            var href = links[j].href || '';
                            if (!href) continue;
                            var m1 = href.match(/story_fbid=(\d+)/);
                            var m2 = href.match(/\/posts\/(\d+)/);
                            var m3 = href.match(/\/permalink\/(\d+)/);
                            if (m1 && m1[1]) { uid = 's:' + m1[1]; break; }
                            if (m2 && m2[1]) { uid = 'p:' + m2[1]; break; }
                            if (m3 && m3[1]) { uid = 'pl:' + m3[1]; break; }
                        }
                        if (!uid) {
                            var txt = (art.innerText || art.textContent || '').trim();
                            if (txt) {
                                var small = txt.slice(0, 180).replace(/\s+/g, ' ');
                                uid = 'txt:' + small;
                            }
                        }
                        if (uid) pushUid(uid);
                    }
                    return out;
                    """,
                    cap,
                ) or []

                for uid in uids:
                    if isinstance(uid, str) and uid:
                        if uid.startswith('txt:'):
                            self.commented_posts_hash.add(hash(uid))
                        else:
                            self.commented_posts_uid.add(uid)
                        seeded += 1
            except Exception as e:
                self._log(f"  ⚠️ [Monitor] Không lấy được baseline nhóm {group_url}: {e}", "warn")

        self._log(f"✅ [Monitor] Đã ghi nhận baseline {seeded} bài hiện có.", "ok")
    
    def _monitor_worker(self):
        """Worker thread for monitoring new posts."""
        interval = self.monitor_interval_var.get() * 60  # Convert to seconds

        def is_action_blocked():
            try:
                return bool(self.driver.execute_script(
                    """
                    var txt = (document.body && (document.body.innerText || document.body.textContent) || '').toLowerCase();
                    if (!txt) return false;
                    var needles = [
                        "you can't do this right now",
                        "temporarily blocked",
                        "try again later",
                        "bạn hiện không thể",
                        "bạn không thể",
                        "tạm thời bị chặn",
                        "hãy thử lại sau"
                    ];
                    for (var i=0;i<needles.length;i++) {
                        if (txt.indexOf(needles[i]) !== -1) return true;
                    }
                    return false;
                    """
                ))
            except Exception:
                return False
        
        while self.is_commenting and self.monitor_thread:
            try:
                self._log(f"🔍 [Monitor] Checking for new posts...", "info")
                
                # Get selected groups
                selected = [url for url, data in self.selected_groups.items() if data['var'].get()]
                comment_text = self._build_comment_text()
                monitor_cap = max(1, int(self.comment_post_count.get() or 1))
                
                # Check each group for new posts
                for group_url in selected:
                    if not self.is_commenting:
                        break

                    if self._is_action_blocked():
                        self._log("⛔ Facebook đang hạn chế thao tác (bị chặn tạm thời). Tự dừng để tránh spam.", "err")
                        self.is_commenting = False
                        break
                    
                    group_name = self.selected_groups[group_url]['name']
                    self._log(f"  🔍 Check: {group_name}", "info")
                    
                    self.driver.get(group_url)
                    time.sleep(2)
                    
                    # Comment on new posts only (check_duplicates=True)
                    # Use smaller count for monitoring (just check recent posts)
                    cmt_count = self._comment_on_group_posts(comment_text, self.comment_image_path.get().strip(),
                                                 post_count=monitor_cap, check_duplicates=True, group_url=group_url)
                    try:
                        self._comment_session_total += int(cmt_count or 0)
                    except Exception:
                        pass
                
                self._log(f"💤 [Monitor] Sleep {interval}s...", "info")
                if self.monitor_stop_event.wait(interval):
                    break
                
            except Exception as e:
                self._log(f"❌ [Monitor] Error: {e}", "err")
                if self.monitor_stop_event.wait(60):
                    break
        
        try:
            total_all = int(getattr(self, "_comment_session_total", 0) or 0)
        except Exception:
            total_all = 0
        self._log(f"🔕 [Monitor] Stopped (tổng comment: {total_all})", "warn")
        self.is_commenting = False
        self.btn_start_comment.configure(state="normal")
    
    def _save_comment_config(self):
        """Save comment configuration to JSON."""
        try:
            config = {
                "comment_texts": [
                    box.get("1.0", "end-1c").strip() for box in (self.comment_textboxes or [])
                ],
                "image_path": self.comment_image_path.get(),
                "image_list": self.comment_images_box.get("1.0", "end-1c").strip() if self.comment_images_box else "",
                "use_templates": bool(self.comment_use_templates_var.get()),
                "use_variation": bool(self.comment_use_variation_var.get()),
                "mode": self.comment_mode_var.get(),
                "comment_old_posts": self.comment_old_posts_var.get(),
                "post_count": self.comment_post_count.get(),
                "comment_delay_min": self.comment_delay_min_var.get(),
                "comment_delay_max": self.comment_delay_max_var.get(),
                "comment_group_rest_min": self.comment_group_rest_min_var.get(),
                "comment_group_rest_max": self.comment_group_rest_max_var.get(),
                "comment_session_group_min": self.comment_session_group_min_var.get(),
                "comment_session_group_max": self.comment_session_group_max_var.get(),
                "comment_session_rest_min": self.comment_session_rest_min_var.get(),
                "comment_session_rest_max": self.comment_session_rest_max_var.get(),
                "monitor_enabled": self.monitor_enabled_var.get(),
                "monitor_interval": self.monitor_interval_var.get(),
                "selected_groups": [url for url, data in self.selected_groups.items() if data['var'].get()],
                "comment_group_text_only": sorted(self.comment_group_text_only),
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self._log(f"💾 Đã lưu cấu hình: {self.config_file}", "ok")
            messagebox.showinfo("Thành công", "Đã lưu cấu hình!")

            try:
                selected_urls = config.get("selected_groups", [])
                groups = [{"name": v.get("name"), "url": k} for k, v in self.selected_groups.items()]
                if groups:
                    self._save_group_cache(self.comment_groups_cache_file, groups, selected_urls)
            except Exception:
                pass
            
        except Exception as e:
            self._log(f"❌ Lỗi lưu config: {e}", "err")

    def _save_group_post_config(self):
        try:
            slots = []
            for s in self.group_post_slots:
                text = ""
                try:
                    tw = s.get("text_widget")
                    if tw is not None:
                        text = tw.get("1.0", "end-1c").strip()
                except Exception:
                    text = ""
                slots.append({
                    "enabled": bool(s["enabled"].get()),
                    "mode": s["mode"].get(),
                    "times": s["times"].get(),
                    "weekday": s["weekday"].get(),
                    "image": s["image"].get(),
                    "text": text,
                })

            config = {
                "slots": slots,
                "mode": self.group_post_mode_var.get(),
                "template_mode": self.group_post_template_mode_var.get(),
                "skip_pending_groups": bool(self.group_post_skip_pending_var.get()),
                "pending_required": self.group_post_pending_required,
                "interval_min": self.group_post_interval_min_var.get(),
                "interval_max": self.group_post_interval_max_var.get(),
                "group_rest_min": self.group_post_group_rest_min_var.get(),
                "group_rest_max": self.group_post_group_rest_max_var.get(),
                "session_group_min": self.group_post_session_group_min_var.get(),
                "session_group_max": self.group_post_session_group_max_var.get(),
                "session_rest_min": self.group_post_session_rest_min_var.get(),
                "session_rest_max": self.group_post_session_rest_max_var.get(),
                "daily_limit": self.group_post_daily_limit_var.get(),
                "selected_groups": list(self.group_post_selected_urls),
                "daily_counts": self.group_post_daily_counts,
            }

            with open(self.group_post_config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self._log(f"💾 [Nhóm] Đã lưu cấu hình: {self.group_post_config_file}", "ok")
            messagebox.showinfo("Thành công", "Đã lưu cấu hình đăng bài nhóm!")

            try:
                if self.group_post_groups_all:
                    self._save_group_cache(self.group_post_groups_cache_file, self.group_post_groups_all, list(self.group_post_selected_urls))
            except Exception:
                pass

        except Exception as e:
            self._log(f"❌ [Nhóm] Lỗi lưu config: {e}", "err")
    
    def _load_comment_config(self):
        """Load comment configuration from JSON."""
        try:
            if not os.path.exists(self.config_file):
                return
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Restore values after UI is built
            self.after(100, lambda: self._apply_loaded_config(config))
            
        except Exception as e:
            print(f"Load config error: {e}")

    def _load_group_post_config(self):
        try:
            if not os.path.exists(self.group_post_config_file):
                return
            with open(self.group_post_config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.after(100, lambda: self._apply_loaded_group_post_config(config))
        except Exception:
            pass

    def _apply_loaded_group_post_config(self, config):
        try:
            if not isinstance(config, dict):
                return

            slots = config.get("slots") or []
            for idx, slot in enumerate(self.group_post_slots):
                if idx >= len(slots):
                    continue
                data = slots[idx] or {}
                try:
                    slot["enabled"].set(bool(data.get("enabled")))
                    slot["mode"].set(data.get("mode") or "daily")
                    slot["times"].set(data.get("times") or "08:00")
                    slot["weekday"].set(data.get("weekday") or "Mon")
                    slot["image"].set(data.get("image") or "")
                    tw = slot.get("text_widget")
                    if tw is not None:
                        tw.delete("1.0", "end")
                        tw.insert("1.0", data.get("text") or "")
                except Exception:
                    pass

            self.group_post_mode_var.set(config.get("mode") or "interval")
            self.group_post_template_mode_var.set(config.get("template_mode") or "sequential")
            self.group_post_skip_pending_var.set(bool(config.get("skip_pending_groups", False)))
            self.group_post_interval_min_var.set(int(config.get("interval_min") or 60))
            self.group_post_interval_max_var.set(int(config.get("interval_max") or 120))
            self.group_post_group_rest_min_var.set(int(config.get("group_rest_min") or 2))
            self.group_post_group_rest_max_var.set(int(config.get("group_rest_max") or 5))
            self.group_post_session_group_min_var.set(int(config.get("session_group_min") or 10))
            self.group_post_session_group_max_var.set(int(config.get("session_group_max") or 20))
            self.group_post_session_rest_min_var.set(int(config.get("session_rest_min") or 30))
            self.group_post_session_rest_max_var.set(int(config.get("session_rest_max") or 60))
            self.group_post_daily_limit_var.set(int(config.get("daily_limit") or 1))

            try:
                pending_map = config.get("pending_required") or {}
                if isinstance(pending_map, dict):
                    self.group_post_pending_required = {str(k): bool(v) for k, v in pending_map.items()}
            except Exception:
                self.group_post_pending_required = {}

            self.group_post_daily_counts = config.get("daily_counts") or {}
            self.group_post_selected_urls = set(config.get("selected_groups") or [])
            if self.group_post_groups_all:
                self._update_group_post_list(self.group_post_groups_all, selected_set=self.group_post_selected_urls, update_source=False)
            self._update_group_post_selected_count()
        except Exception:
            pass
    
    def _apply_loaded_config(self, config):
        """Apply loaded config to UI."""
        try:
            if self.comment_textboxes:
                texts = config.get("comment_texts") if isinstance(config, dict) else None
                if isinstance(texts, list) and texts:
                    for idx, box in enumerate(self.comment_textboxes):
                        box.delete("1.0", "end")
                        if idx < len(texts):
                            box.insert("1.0", texts[idx])
                elif 'comment_text' in config:
                    # Backward compatibility: put old single text into the first box.
                    self.comment_textboxes[0].delete("1.0", "end")
                    self.comment_textboxes[0].insert("1.0", config['comment_text'])
            
            if 'image_path' in config:
                self.comment_image_path.set(config['image_path'])

            if self.comment_images_box is not None and 'image_list' in config:
                self.comment_images_box.delete("1.0", "end")
                self.comment_images_box.insert("1.0", config.get('image_list') or "")

            if 'use_templates' in config:
                self.comment_use_templates_var.set(bool(config['use_templates']))

            if 'use_variation' in config:
                self.comment_use_variation_var.set(bool(config['use_variation']))
            
            if 'mode' in config:
                self.comment_mode_var.set(config['mode'])

            if 'comment_old_posts' in config:
                self.comment_old_posts_var.set(bool(config['comment_old_posts']))
            
            if 'post_count' in config:
                self.comment_post_count.set(config['post_count'])

            if 'comment_delay_min' in config:
                self.comment_delay_min_var.set(config['comment_delay_min'])

            if 'comment_delay_max' in config:
                self.comment_delay_max_var.set(config['comment_delay_max'])

            if 'comment_group_rest_min' in config:
                self.comment_group_rest_min_var.set(config['comment_group_rest_min'])

            if 'comment_group_rest_max' in config:
                self.comment_group_rest_max_var.set(config['comment_group_rest_max'])

            if 'comment_session_group_min' in config:
                self.comment_session_group_min_var.set(config['comment_session_group_min'])

            if 'comment_session_group_max' in config:
                self.comment_session_group_max_var.set(config['comment_session_group_max'])

            if 'comment_session_rest_min' in config:
                self.comment_session_rest_min_var.set(config['comment_session_rest_min'])

            if 'comment_session_rest_max' in config:
                self.comment_session_rest_max_var.set(config['comment_session_rest_max'])
            
            if 'monitor_enabled' in config:
                self.monitor_enabled_var.set(config['monitor_enabled'])
            
            if 'monitor_interval' in config:
                self.monitor_interval_var.set(config['monitor_interval'])

            if 'selected_groups' in config:
                try:
                    self._pending_selected_group_urls = set(config.get('selected_groups') or [])
                except Exception:
                    self._pending_selected_group_urls = set()

            if 'comment_group_text_only' in config:
                try:
                    self.comment_group_text_only = set(config.get('comment_group_text_only') or [])
                except Exception:
                    self.comment_group_text_only = set()

            self._update_comment_selected_count()
            
            self._log("📂 Đã load cấu hình", "info")
            
        except Exception as e:
            print(f"Apply config error: {e}")

    # ── Config cho tab duyệt bài nhóm ───────────────────────────────────────
    def _save_approval_config(self):
        """Lưu cấu hình duyệt bài (từ khoá, chế độ, chu kỳ) ra JSON."""
        try:
            keywords = ""
            try:
                if self.approval_keywords_box is not None:
                    keywords = self.approval_keywords_box.get("1.0", "end-1c")
            except Exception:
                keywords = ""

            config = {
                "keywords": keywords,
                "mode": self.approval_mode_var.get(),
                "interval": int(self.approval_interval_var.get() or 5),
                "auto_approve_safe": bool(self.approval_auto_approve_safe.get()),
                "selected_groups": [url for url, data in self.approval_selected_groups.items() if data['var'].get()],
            }

            with open(self.approval_config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self._log(f"💾 Đã lưu cấu hình duyệt bài: {self.approval_config_file}", "ok")
            messagebox.showinfo("Thành công", "Đã lưu cấu hình duyệt bài nhóm.")

            try:
                selected_urls = [url for url, data in self.approval_selected_groups.items() if data['var'].get()]
                groups = [{"name": v.get("name"), "url": k} for k, v in self.approval_selected_groups.items()]
                if groups:
                    self._save_group_cache(self.approval_groups_cache_file, groups, selected_urls)
            except Exception:
                pass
        except Exception as e:
            self._log(f"❌ Lỗi lưu cấu hình duyệt bài: {e}", "err")

    def _load_approval_config(self):
        """Đọc cấu hình duyệt bài từ JSON và áp dụng vào UI sau khi build."""
        try:
            if not os.path.exists(self.approval_config_file):
                return

            with open(self.approval_config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            def _apply():
                try:
                    if self.approval_keywords_box is not None and "keywords" in config:
                        self.approval_keywords_box.delete("1.0", "end")
                        self.approval_keywords_box.insert("1.0", config.get("keywords", ""))

                    if "mode" in config:
                        self.approval_mode_var.set(config.get("mode", "interval"))

                    if "interval" in config:
                        self.approval_interval_var.set(int(config.get("interval", 5)))

                    if "auto_approve_safe" in config:
                        self.approval_auto_approve_safe.set(bool(config.get("auto_approve_safe", True)))

                    if "selected_groups" in config:
                        try:
                            self._pending_selected_approval_urls = set(config.get("selected_groups") or [])
                        except Exception:
                            self._pending_selected_approval_urls = set()

                    self._log("📂 Đã load cấu hình duyệt bài nhóm", "info")
                except Exception:
                    pass

            # Delay nhẹ để đảm bảo UI đã build xong
            self.after(200, _apply)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    def _on_close(self):
        try:
            self.scheduler_stop_event.set()
        except Exception:
            pass
        if self.driver:
            try: self.driver.quit()
            except Exception: pass
        self.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FB Text Fixer - Multi-profile support")
    parser.add_argument("--profile", "-p", type=str, default="default",
                        help="Profile name (e.g. acc1, acc2). Each profile has separate config and Chrome session.")
    args = parser.parse_args()
    App(profile_name=args.profile).mainloop()

