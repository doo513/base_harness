"""Tkinter desktop GUI for Harness Workbench.

Provides a 4-tab operator dashboard:
1. Diagnostics: OS/WSL identity, Python/Bun, Harness root, AGY, sanitized proxies, TLS check.
2. Run: Execution configuration, redacted command preview, safe single process launch (no retry, no kill).
3. Live Status: Prepare/Explore/Execute/Verify stages, actor, model, sub-agent counts, outcome, stale alert.
4. Event Log: Chronological timeline of observed lifecycle events.
"""

from __future__ import annotations

import os
import pathlib
import sys
import threading
import time
from typing import Any, Callable

from data import (
    DEFAULT_BACKEND,
    DEFAULT_DOMAIN,
    DEFAULT_MODEL,
    DOMAINS,
    KNOWN_BACKENDS,
    KNOWN_MODELS,
    SAFETY_PRINCIPLES,
    STAGES,
)
from workbench import (
    DataRedactor,
    ProcessRecord,
    RunConfig,
    check_tls_reachability,
    diagnose_environment,
    evaluate_backend_boundary,
    get_live_status,
    launch_base_harness,
)

# Safe Tkinter import (graceful fallback if running in headless Linux environment)
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]


class WorkbenchGUI:
    """Tkinter-based Harness Workbench application."""

    def __init__(
        self,
        config: RunConfig | None = None,
        monitor_path: str | pathlib.Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_s: float = 2.0,
    ) -> None:
        if not HAS_TKINTER:
            raise RuntimeError(
                "Tkinter is not available in the current Python environment.\n"
                "To use the GUI on Windows, ensure Python is installed with Tcl/Tk support.\n"
                "On WSL/Linux, install python3-tk or run workbench.py with CLI flags (--diagnose, --status, --preview)."
            )

        self.root = tk.Tk()
        self.root.title("Base Harness Workbench (Operator Aid)")
        self.root.geometry("1180x820")
        self.root.minsize(960, 640)

        self.config = config or RunConfig(workspace="", harness_root="")
        self.monitor_path = monitor_path
        self.auto_refresh = auto_refresh
        self.refresh_interval_ms = int(refresh_interval_s * 1000)

        self.last_process: ProcessRecord | None = None
        self.diag_data: dict[str, Any] = {}
        self.status_data: dict[str, Any] = {}

        self._setup_styles()
        self._build_header()
        self._build_tabs()

        # Initial data load
        self.refresh_diagnostics()
        self.refresh_live_status()
        self.update_command_preview()

        if self.auto_refresh:
            self.root.after(self.refresh_interval_ms, self._on_auto_refresh)

    def mainloop(self) -> None:
        self.root.mainloop()

    # -----------------------------------------------------------------------
    # Styling & Theming
    # -----------------------------------------------------------------------
    def _setup_styles(self) -> None:
        self.style = ttk.Style(self.root)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        # Color Palette
        bg_dark = "#17202a"
        card_bg = "#212f3d"
        text_white = "#f8f9f9"
        text_muted = "#aeb6bf"

        self.style.configure(".", background=bg_dark, foreground=text_white, font=("Segoe UI", 9))
        self.style.configure("TNotebook", background=bg_dark)
        self.style.configure("TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10, "bold"))
        self.style.configure("TFrame", background=bg_dark)
        self.style.configure("Card.TFrame", background=card_bg, relief="solid", borderwidth=1)
        self.style.configure("Header.TFrame", background="#0e1726")
        self.style.configure("HeaderTitle.TLabel", background="#0e1726", foreground="#ffffff", font=("Segoe UI", 16, "bold"))
        self.style.configure("HeaderSub.TLabel", background="#0e1726", foreground="#85929e", font=("Segoe UI", 9))

        self.style.configure("Badge.TFrame", background="#2c3e50", relief="solid", borderwidth=1)
        self.style.configure("BadgeTitle.TLabel", background="#2c3e50", foreground="#aeb6bf", font=("Segoe UI", 8))
        self.style.configure("BadgeVal.TLabel", background="#2c3e50", foreground="#ffffff", font=("Segoe UI", 11, "bold"))

        self.style.configure("Warn.TLabel", foreground="#f39c12", font=("Segoe UI", 9, "bold"))
        self.style.configure("Err.TLabel", foreground="#e74c3c", font=("Segoe UI", 9, "bold"))
        self.style.configure("Ok.TLabel", foreground="#2ecc71", font=("Segoe UI", 9, "bold"))

    # -----------------------------------------------------------------------
    # Header Banner
    # -----------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(16, 10), style="Header.TFrame")
        header.pack(side="top", fill="x")

        # Title & Subtitle
        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side="left", fill="y")
        ttk.Label(title_box, text="Base Harness Workbench", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Operator Aid · Evidence-Only Semantics · Safe by Default (No Kill / No Retry)",
            style="HeaderSub.TLabel",
        ).pack(anchor="w")

        # Boundary Warning / Status Pill in Header
        self.boundary_pill = tk.Label(
            header,
            text="CHECKING BOUNDARY...",
            font=("Segoe UI", 9, "bold"),
            bg="#34495e",
            fg="#ffffff",
            padx=12,
            pady=4,
            relief="solid",
            bd=1,
        )
        self.boundary_pill.pack(side="right", padx=(10, 0))

    # -----------------------------------------------------------------------
    # Tabs Construction
    # -----------------------------------------------------------------------
    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        # 4 Tabs
        self.tab_diag = ttk.Frame(self.notebook, padding=10)
        self.tab_run = ttk.Frame(self.notebook, padding=10)
        self.tab_status = ttk.Frame(self.notebook, padding=10)
        self.tab_events = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_diag, text=" 1. 환경 진단 (Diagnostics) ")
        self.notebook.add(self.tab_run, text=" 2. 실행 설정 (Run Console) ")
        self.notebook.add(self.tab_status, text=" 3. 실시간 상태 (Live Status) ")
        self.notebook.add(self.tab_events, text=" 4. 이벤트 로그 (Event Log) ")

        self._build_diagnostics_tab()
        self._build_run_tab()
        self._build_live_status_tab()
        self._build_event_log_tab()

    # -----------------------------------------------------------------------
    # Tab 1: Diagnostics
    # -----------------------------------------------------------------------
    def _build_diagnostics_tab(self) -> None:
        top_bar = ttk.Frame(self.tab_diag)
        top_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(top_bar, text="새로고침 (Refresh)", command=self.refresh_diagnostics).pack(side="left")
        ttk.Button(top_bar, text="TLS 도달성 재확인 (Test TLS)", command=self._recheck_tls).pack(side="left", padx=10)

        # Boundary Alert Box
        self.boundary_alert_box = tk.Label(
            self.tab_diag,
            text="",
            justify="left",
            anchor="w",
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            padx=10,
            pady=8,
        )
        self.boundary_alert_box.pack(fill="x", pady=(0, 10))

        # Diagnostics Text / Cards Area
        self.diag_text = tk.Text(
            self.tab_diag,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            bg="#101722",
            fg="#e7edf7",
            relief="solid",
            bd=1,
        )
        self.diag_text.pack(fill="both", expand=True)

    def refresh_diagnostics(self) -> None:
        self.diag_data = diagnose_environment(
            harness_root=self.config.harness_root,
            agy_binary=self.config.agy_binary,
            model=self.config.model,
            backend=self.config.backend,
        )
        boundary = self.diag_data.get("boundary", {})
        is_matched = boundary.get("is_matched", False)

        if is_matched:
            self.boundary_pill.config(
                text=f"✓ {boundary.get('label', 'Clean Boundary')}",
                bg="#27ae60",
                fg="#ffffff",
            )
            self.boundary_alert_box.config(
                text=f"✓ [백엔드 격리 검증 완료] {boundary.get('label')}\n"
                f"{boundary.get('description')}",
                bg="#193324",
                fg="#2ecc71",
            )
        else:
            self.boundary_pill.config(
                text=f"⚠ {boundary.get('label', 'Boundary Mismatch')}",
                bg="#c0392b",
                fg="#ffffff",
            )
            self.boundary_alert_box.config(
                text=f"⚠ [백엔드 경계 경고: 환경 불일치 감지!]\n"
                f"{boundary.get('description')}\n"
                f"경고: {boundary.get('warning')}",
                bg="#3d1e1e",
                fg="#ff7675",
            )

        # Update formatted text
        from workbench import format_diagnostics_text
        text_content = format_diagnostics_text(self.diag_data)
        self.diag_text.config(state="normal")
        self.diag_text.delete("1.0", tk.END)
        self.diag_text.insert(tk.END, text_content)
        self.diag_text.config(state="disabled")

    def _recheck_tls(self) -> None:
        tls = check_tls_reachability()
        self.diag_data["tlsReachability"] = tls
        from workbench import format_diagnostics_text
        text_content = format_diagnostics_text(self.diag_data)
        self.diag_text.config(state="normal")
        self.diag_text.delete("1.0", tk.END)
        self.diag_text.insert(tk.END, text_content)
        self.diag_text.config(state="disabled")
        if tls.get("reachable"):
            messagebox.showinfo("TLS 검사 성공", f"oauth2.googleapis.com:443 연결 성공!\n지연 시간: {tls.get('latency_ms')} ms\n암호 스위트: {tls.get('cipher')}")
        else:
            messagebox.showwarning("TLS 검사 실패 / 오프라인", f"oauth2.googleapis.com:443 연결 불가.\n상세: {tls.get('error')}")

    # -----------------------------------------------------------------------
    # Tab 2: Run Console
    # -----------------------------------------------------------------------
    def _build_run_tab(self) -> None:
        # Form Container
        form_frame = ttk.LabelFrame(self.tab_run, text="Base Harness 실행 파라미터", padding=10)
        form_frame.pack(fill="x", pady=(0, 10))

        # Fields: Workspace, Harness Root, Domain, Backend, Model, Goal File, Log File
        self.var_workspace = tk.StringVar(value=str(self.config.workspace))
        self.var_harness_root = tk.StringVar(value=str(self.config.harness_root))
        self.var_domain = tk.StringVar(value=self.config.domain)
        self.var_backend = tk.StringVar(value=self.config.backend)
        self.var_model = tk.StringVar(value=self.config.model)
        self.var_goal_file = tk.StringVar(value=str(self.config.goal_file))
        self.var_log_file = tk.StringVar(value=str(self.config.log_file))
        self.var_agy_binary = tk.StringVar(value=str(self.config.agy_binary or ""))

        rows = [
            ("대상 작업 공간 (Workspace):", self.var_workspace, self._browse_workspace),
            ("하네스 루트 경로 (Harness Root):", self.var_harness_root, self._browse_harness_root),
            ("목표 파일 (Goal File):", self.var_goal_file, self._browse_goal_file),
            ("로그 출력 파일 (Log File):", self.var_log_file, self._browse_log_file),
            ("AGY 실행 바이너리 (AGY Binary):", self.var_agy_binary, self._browse_agy_binary),
        ]

        for idx, (label_text, var, browse_fn) in enumerate(rows):
            ttk.Label(form_frame, text=label_text).grid(row=idx, column=0, sticky="w", pady=3)
            entry = ttk.Entry(form_frame, textvariable=var, width=65)
            entry.grid(row=idx, column=1, sticky="ew", padx=6, pady=3)
            entry.bind("<KeyRelease>", lambda e: self.update_command_preview())
            ttk.Button(form_frame, text="찾아보기...", command=browse_fn).grid(row=idx, column=2, padx=4, pady=3)

        # Domain, Backend, Model row
        opts_frame = ttk.Frame(form_frame)
        opts_frame.grid(row=len(rows), column=0, columnspan=3, sticky="ew", pady=(6, 0))

        ttk.Label(opts_frame, text="도메인:").pack(side="left")
        dom_combo = ttk.Combobox(opts_frame, textvariable=self.var_domain, values=DOMAINS, width=12, state="readonly")
        dom_combo.pack(side="left", padx=(4, 16))
        dom_combo.bind("<<ComboboxSelected>>", lambda e: self.update_command_preview())

        ttk.Label(opts_frame, text="백엔드:").pack(side="left")
        bk_combo = ttk.Combobox(opts_frame, textvariable=self.var_backend, values=KNOWN_BACKENDS, width=16)
        bk_combo.pack(side="left", padx=(4, 16))
        bk_combo.bind("<<ComboboxSelected>>", lambda e: self.update_command_preview())
        bk_combo.bind("<KeyRelease>", lambda e: self.update_command_preview())

        ttk.Label(opts_frame, text="모델:").pack(side="left")
        md_combo = ttk.Combobox(opts_frame, textvariable=self.var_model, values=KNOWN_MODELS, width=24)
        md_combo.pack(side="left", padx=(4, 6))
        md_combo.bind("<<ComboboxSelected>>", lambda e: self.update_command_preview())
        md_combo.bind("<KeyRelease>", lambda e: self.update_command_preview())

        form_frame.columnconfigure(1, weight=1)

        # Preview Frame
        preview_box = ttk.LabelFrame(self.tab_run, text="명령어 미리보기 (인증 정보 완전 마스킹)", padding=8)
        preview_box.pack(fill="both", expand=True, pady=(0, 10))

        self.preview_text = tk.Text(
            preview_box,
            height=8,
            font=("Consolas", 9),
            bg="#101722",
            fg="#a9dfbf",
            relief="solid",
            bd=1,
        )
        self.preview_text.pack(fill="both", expand=True)

        # Control Bar: Start Button & Safety Guarantee
        ctrl_frame = ttk.Frame(self.tab_run)
        ctrl_frame.pack(fill="x")

        self.btn_start = tk.Button(
            ctrl_frame,
            text="▶ Base Harness 단일 실행 (Start Process)",
            font=("Segoe UI", 10, "bold"),
            bg="#2980b9",
            fg="#ffffff",
            padx=14,
            pady=6,
            relief="raised",
            command=self._on_start_process,
        )
        self.btn_start.pack(side="left")

        # Safety Notice Label
        safety_notice = tk.Label(
            ctrl_frame,
            text="안전 원칙: 자동 재시도 루프 없음 · 프로세스 강제 종료(Kill) 기능 없음 · Operator Aid 전용",
            font=("Segoe UI", 9, "italic"),
            bg="#2c3e50",
            fg="#f39c12",
            padx=10,
            pady=6,
        )
        safety_notice.pack(side="left", padx=14)

        # Last Process Status Display
        self.proc_status_label = ttk.Label(ctrl_frame, text="실행 중인 프로세스 없음", font=("Segoe UI", 9, "bold"))
        self.proc_status_label.pack(side="right")

    def _browse_workspace(self) -> None:
        path = filedialog.askdirectory(title="대상 작업 공간 선택", initialdir=self.var_workspace.get())
        if path:
            self.var_workspace.set(path)
            self.update_command_preview()

    def _browse_harness_root(self) -> None:
        path = filedialog.askdirectory(title="하네스 루트 디렉터리 선택", initialdir=self.var_harness_root.get())
        if path:
            self.var_harness_root.set(path)
            self.update_command_preview()

    def _browse_goal_file(self) -> None:
        path = filedialog.askopenfilename(title="목표 파일 선택", initialdir=os.path.dirname(self.var_goal_file.get()))
        if path:
            self.var_goal_file.set(path)
            self.update_command_preview()

    def _browse_log_file(self) -> None:
        path = filedialog.asksaveasfilename(title="로그 출력 파일 선택", initialdir=os.path.dirname(self.var_log_file.get()))
        if path:
            self.var_log_file.set(path)
            self.update_command_preview()

    def _browse_agy_binary(self) -> None:
        path = filedialog.askopenfilename(title="AGY 바이너리 선택")
        if path:
            self.var_agy_binary.set(path)
            self.update_command_preview()
            self.refresh_diagnostics()

    def update_command_preview(self) -> None:
        self.config = RunConfig(
            workspace=self.var_workspace.get(),
            harness_root=self.var_harness_root.get(),
            domain=self.var_domain.get(),
            backend=self.var_backend.get(),
            model=self.var_model.get(),
            goal_file=self.var_goal_file.get(),
            log_file=self.var_log_file.get(),
            agy_binary=self.var_agy_binary.get(),
        )
        preview = self.config.build_command_preview()
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, preview)
        self.preview_text.config(state="disabled")

    def _on_start_process(self) -> None:
        if self.last_process and self.last_process.is_running:
            if not messagebox.askyesno("경고", "이미 실행 중인 Base Harness 프로세스가 있습니다.\n새 프로세스를 추가로 실행하시겠습니까?"):
                return

        self.update_command_preview()
        try:
            record = launch_base_harness(self.config)
            self.last_process = record
            self.proc_status_label.config(
                text=f"PID: {record.pid} 실행 중 (시작: {record.start_time.split('T')[1][:8]})",
                style="Ok.TLabel",
            )
            messagebox.showinfo(
                "Base Harness 실행됨",
                f"Base Harness가 성공적으로 시작되었습니다.\n\n"
                f"PID: {record.pid}\n"
                f"로그 파일: {record.log_path}\n\n"
                f"안전 알림: 자동 재시도 루프가 없으며, kill 기능은 제공되지 않습니다.",
            )
        except Exception as exc:
            messagebox.showerror("실행 실패", f"프로세스 시작 실패: {exc}")

    # -----------------------------------------------------------------------
    # Tab 3: Live Status
    # -----------------------------------------------------------------------
    def _build_live_status_tab(self) -> None:
        top_bar = ttk.Frame(self.tab_status)
        top_bar.pack(fill="x", pady=(0, 10))

        ttk.Button(top_bar, text="새로고침 (Refresh)", command=self.refresh_live_status).pack(side="left")

        self.var_auto_refresh = tk.BooleanVar(value=self.auto_refresh)
        ttk.Checkbutton(
            top_bar,
            text="2초 자동 갱신 (Auto Refresh)",
            variable=self.var_auto_refresh,
            command=self._toggle_auto_refresh,
        ).pack(side="left", padx=16)

        # Stale warning pill
        self.stale_pill = tk.Label(
            top_bar,
            text="",
            font=("Segoe UI", 9, "bold"),
            bg="#2c3e50",
            fg="#ffffff",
            padx=10,
            pady=3,
        )
        self.stale_pill.pack(side="right")

        # Badges Row (Domain, Stage, Phase, Actor, Model, Outcome)
        badge_frame = ttk.Frame(self.tab_status)
        badge_frame.pack(fill="x", pady=(0, 10))

        self.status_badges: dict[str, tk.Label] = {}
        items = ("domain", "stage", "phase", "actor", "model", "outcome")
        for i, key in enumerate(items):
            badge_frame.columnconfigure(i, weight=1)
            b_box = tk.Frame(badge_frame, bg="#212f3d", relief="solid", bd=1, padx=8, pady=6)
            b_box.grid(row=0, column=i, sticky="ew", padx=3)
            tk.Label(b_box, text=key.upper(), font=("Segoe UI", 8), bg="#212f3d", fg="#aeb6bf").pack(anchor="w")
            lbl = tk.Label(b_box, text="—", font=("Segoe UI", 11, "bold"), bg="#212f3d", fg="#ffffff")
            lbl.pack(anchor="w")
            self.status_badges[key] = lbl

        # Stage Progress Visualizer
        stage_frame = ttk.LabelFrame(self.tab_status, text="하네스 4단계 라이프사이클 (Prepare → Explore → Execute → Verify)", padding=8)
        stage_frame.pack(fill="x", pady=(0, 10))

        self.stage_pills: dict[str, tk.Label] = {}
        stage_row = ttk.Frame(stage_frame)
        stage_row.pack(fill="x")
        for idx, s in enumerate(STAGES):
            stage_row.columnconfigure(idx, weight=1)
            pill = tk.Label(
                stage_row,
                text=f"○ {s['label']} ({s['ko']})",
                font=("Segoe UI", 10, "bold"),
                bg="#1a252f",
                fg="#7f8c8d",
                relief="solid",
                bd=1,
                pady=6,
            )
            pill.grid(row=0, column=idx, sticky="ew", padx=4)
            self.stage_pills[s["id"]] = pill

        # Metrics & Subagents Frame
        subagent_frame = ttk.LabelFrame(self.tab_status, text="보조 에이전트 (Sub-agents) 및 최근 상태", padding=10)
        subagent_frame.pack(fill="both", expand=True)

        self.subagent_summary = tk.Label(
            subagent_frame,
            text="",
            justify="left",
            anchor="w",
            font=("Consolas", 10),
            bg="#101722",
            fg="#e7edf7",
            padx=10,
            pady=10,
            relief="solid",
            bd=1,
        )
        self.subagent_summary.pack(fill="both", expand=True)

    def _toggle_auto_refresh(self) -> None:
        self.auto_refresh = self.var_auto_refresh.get()

    def _on_auto_refresh(self) -> None:
        if self.auto_refresh:
            self.refresh_live_status()
            # Update process status if one was started
            if self.last_process:
                code = self.last_process.exit_code
                if code is not None:
                    self.proc_status_label.config(
                        text=f"PID: {self.last_process.pid} 종료됨 (종료코드: {code})",
                        style="Warn.TLabel" if code != 0 else "Ok.TLabel",
                    )
                else:
                    self.proc_status_label.config(
                        text=f"PID: {self.last_process.pid} 실행 중",
                        style="Ok.TLabel",
                    )
        if self.root.winfo_exists():
            self.root.after(self.refresh_interval_ms, self._on_auto_refresh)

    def refresh_live_status(self) -> None:
        self.status_data = get_live_status(
            workspace=self.config.workspace,
            harness_root=self.config.harness_root,
            log_file=self.config.log_file,
            monitor_path=self.monitor_path,
        )
        # Update Badges
        self.status_badges["domain"].config(text=str(self.status_data.get("domainLabel", "—")))
        self.status_badges["stage"].config(text=str(self.status_data.get("stageLabel", "—")))
        self.status_badges["phase"].config(text=str(self.status_data.get("phase", "—")))
        self.status_badges["actor"].config(text=str(self.status_data.get("actorLabel", "—")))
        self.status_badges["model"].config(text=str(self.status_data.get("model", "—")))
        self.status_badges["outcome"].config(text=str(self.status_data.get("outcome", "—")))

        # Update Stages Visualizer
        curr_stage = self.status_data.get("stage", "prepare")
        for s in STAGES:
            sid = s["id"]
            if sid == curr_stage:
                self.stage_pills[sid].config(
                    text=f"● {s['label']} ({s['ko']})",
                    bg="#2980b9",
                    fg="#ffffff",
                )
            else:
                self.stage_pills[sid].config(
                    text=f"○ {s['label']} ({s['ko']})",
                    bg="#1a252f",
                    fg="#7f8c8d",
                )

        # Stale Pill
        is_stale = self.status_data.get("stale", False)
        if is_stale:
            self.stale_pill.config(text="⚠ STALE (기록 정체)", bg="#d35400", fg="#ffffff")
        else:
            self.stale_pill.config(text="● LIVE (동작 관측)", bg="#27ae60", fg="#ffffff")

        # Subagent Summary & Warnings
        sub = self.status_data.get("subagents", {})
        ev = self.status_data.get("latestEvent") or {}
        warns = "\n".join(f"• 경고: {w}" for w in self.status_data.get("warnings", []))
        summary_text = (
            f"출처(Source)           : {self.status_data.get('source')}\n"
            f"서브에이전트 호출 총계 : {sub.get('called', 0)} 회 (대기: {sub.get('queued', 0)} / 활성: {sub.get('active', 0)} / 실패: {sub.get('failed', 0)})\n"
            f"최근 이벤트 시각       : {ev.get('timestamp', '—')}\n"
            f"최근 이벤트 유형       : {ev.get('type', '—')} (단계: {ev.get('phase', '—')})\n"
            f"상세 결과 / 결함 종류  : {ev.get('failureKind') or ev.get('outcome') or '—'}\n"
        )
        if warns:
            summary_text += f"\n{warns}\n"

        self.subagent_summary.config(text=summary_text)

        # Refresh Event Log Tab list
        self._refresh_event_log_tab()

    # -----------------------------------------------------------------------
    # Tab 4: Event Log
    # -----------------------------------------------------------------------
    def _build_event_log_tab(self) -> None:
        top_bar = ttk.Frame(self.tab_events)
        top_bar.pack(fill="x", pady=(0, 8))
        ttk.Button(top_bar, text="새로고침 (Refresh)", command=self.refresh_live_status).pack(side="left")

        # Treeview for Events
        tree_frame = ttk.Frame(self.tab_events)
        tree_frame.pack(fill="both", expand=True)

        columns = ("timestamp", "type", "phase", "outcome", "failureKind")
        self.event_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        headings = {
            "timestamp": "타임스탬프 (Timestamp)",
            "type": "이벤트 종류 (Type)",
            "phase": "단계 (Phase)",
            "outcome": "결과 (Outcome)",
            "failureKind": "오류/결함 종류 (Failure Kind)",
        }
        for col, title in headings.items():
            self.event_tree.heading(col, text=title)

        self.event_tree.column("timestamp", width=180)
        self.event_tree.column("type", width=130)
        self.event_tree.column("phase", width=140)
        self.event_tree.column("outcome", width=100)
        self.event_tree.column("failureKind", width=180)

        self.event_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.event_tree.yview)
        scroll.pack(side="right", fill="y")
        self.event_tree.configure(yscrollcommand=scroll.set)

    def _refresh_event_log_tab(self) -> None:
        # Clear existing
        for item in self.event_tree.get_children():
            self.event_tree.delete(item)

        events = self.status_data.get("events") or []
        for ev in reversed(events):
            self.event_tree.insert(
                "",
                "end",
                values=(
                    ev.get("timestamp", ""),
                    ev.get("type", ""),
                    ev.get("phase", ""),
                    ev.get("outcome", ""),
                    ev.get("failureKind", ""),
                ),
            )
