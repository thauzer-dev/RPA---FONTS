"""Hub de orquestração — executa sequencialmente um conjunto de scripts
Python responsáveis por atualizar as fontes de dados usadas pelos
relatórios internos, com acompanhamento visual do progresso e logging
em arquivo.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

BASE_RPA_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_RPA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ARQUIVO_LOG = LOG_DIR / f"rpa_fontes_dados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)
LOGGER = logging.getLogger(__name__)

APP_TITLE = "Hub de Atualização - Fontes de Dados"
APP_SUBTITLE = "Execução orquestrada e monitorada das rotinas de atualização de bases corporativas"

# Caminho raiz do compartilhamento de rede onde os scripts de origem estão
# hospedados. Ajuste o valor abaixo (ou defina a variável de ambiente
# RPA_SHARE_ROOT) para o caminho real do seu ambiente. Manter esse tipo de
# informação fora do código-fonte evita expor a estrutura interna da rede
# em repositórios públicos.
SHARE_ROOT = os.environ.get(
    "RPA_SHARE_ROOT",
    r"\\SEU-SERVIDOR\planilha\Inteligencia_Comercial\Automacoes",
)

SCRIPTS: list[dict[str, str]] = [
    {
        "name": "Base 1",
        "directory": rf"{SHARE_ROOT}\Informes de Vendas\Bases - Informes",
        "description": "Atualizando o arquivo consolidador dos Informes de Vendas - 2R",
    },
    {
        "name": "Base 2",
        "directory": rf"{SHARE_ROOT}\Informes de Vendas",
        "description": "Atualizando a Base de Estoque - 2R para os Informes de Vendas - 2R",
    },
    {
        "name": "Base 3",
        "directory": rf"{SHARE_ROOT}\Informes de Vendas",
        "description": "Atualizando a Base de Vendas - 2R para os Informes de Vendas - 2R",
    },
]


# ─── Utilitários ─────────────────────────────────────────────────────────
def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def validate_script(info: dict[str, str]) -> tuple[bool, str]:
    directory = Path(info["directory"])
    path = directory / info["name"]
    if not directory.exists():
        return False, f"Diretório não encontrado: {directory}"
    if not path.exists():
        return False, f"Script não encontrado: {path}"
    if not path.is_file():
        return False, f"O caminho informado não é um arquivo: {path}"
    return True, str(path)


class RPAFontesApp(tk.Tk):
    BG = "#101114"
    PANEL = "#17191F"
    PANEL_DARK = "#13161C"
    CARD = "#1B1F27"
    CARD_ALT = "#232833"
    LOG_BG = "#0E1015"
    ACCENT = "#E10600"
    TEXT = "#FFFFFF"
    TEXT_SOFT = "#D5D7DC"
    TEXT_MUTED = "#8F96A3"
    BORDER = "#2A2D34"
    SUCCESS = "#22C55E"
    WARNING = "#F59E0B"
    ERROR = "#FF4D4F"
    INACTIVE = "#4B5563"

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x790")
        self.minsize(1120, 700)
        self.configure(bg=self.BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events = queue.Queue()
        self.worker_thread = None
        self.current_process = None
        self.cancel_requested = False
        self.running = False
        self.started_at = None
        self.executed_count = 0

        self.status_var = tk.StringVar(value="Sistema pronto para iniciar")
        self.detail_var = tk.StringVar(
            value="Execute a rotina para atualizar sequencialmente as fontes de dados."
        )
        self.badge_var = tk.StringVar(value="RPA AGUARDANDO")
        self.progress_text_var = tk.StringVar(value=f"0 / {len(SCRIPTS)}")
        self.percent_var = tk.StringVar(value="0%")
        self.timer_var = tk.StringVar(value="00:00")
        self.current_script_var = tk.StringVar(value="Nenhum processo em execução")
        self.step_dots = []
        self.step_labels = []

        self._configure_styles()
        self._build_ui()
        self.after(100, self._process_events)
        self.after(500, self._update_timer)

    # ─── Estilos e construção da interface ─────────────────────────────────
    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=self.BORDER,
            background=self.ACCENT,
            darkcolor=self.ACCENT,
            lightcolor=self.ACCENT,
            bordercolor=self.BORDER,
            thickness=18,
        )
        style.configure(
            "Primary.TButton",
            background=self.ACCENT,
            foreground=self.TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(14, 9),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#5B2020"), ("active", "#B80500"), ("pressed", "#930400")],
            foreground=[("disabled", "#B9B9B9")],
        )
        style.configure(
            "Secondary.TButton",
            background=self.BORDER,
            foreground=self.TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(12, 9),
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Secondary.TButton", background=[("active", "#3A3E47"), ("pressed", "#20232A")])
        style.configure(
            "Danger.TButton",
            background="#3A2022",
            foreground="#FFD7D7",
            borderwidth=0,
            focusthickness=0,
            padding=(12, 9),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Danger.TButton",
            background=[("disabled", "#282022"), ("active", "#5A2629"), ("pressed", "#2B1718")],
            foreground=[("disabled", "#777777")],
        )

    def _build_ui(self):
        header = tk.Frame(self, bg=self.BG)
        header.pack(fill="x", padx=20, pady=(18, 10))

        self.badge_label = tk.Label(
            header,
            textvariable=self.badge_var,
            bg=self.WARNING,
            fg=self.TEXT,
            font=("Segoe UI", 9, "bold"),
            padx=11,
            pady=5,
        )
        self.badge_label.pack(anchor="w", pady=(0, 9))
        tk.Label(
            header, text=APP_TITLE, bg=self.BG, fg=self.TEXT, font=("Segoe UI", 25, "bold")
        ).pack(anchor="w")
        tk.Label(
            header, text=APP_SUBTITLE, bg=self.BG, fg=self.TEXT_SOFT, font=("Segoe UI", 12)
        ).pack(anchor="w", pady=(4, 0))

        controls = tk.Frame(self, bg=self.BG)
        controls.pack(fill="x", padx=20, pady=(0, 10))
        self.start_button = ttk.Button(
            controls,
            text="Executar atualização",
            command=self.start_execution,
            style="Primary.TButton",
        )
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(
            controls,
            text="Interromper",
            command=self.cancel_execution,
            style="Danger.TButton",
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(7, 0))
        ttk.Button(
            controls,
            text="Abrir pasta de logs",
            command=self.open_log_folder,
            style="Secondary.TButton",
        ).pack(side="left", padx=(7, 0))

        body = tk.Frame(self, bg=self.BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        left = tk.Frame(body, bg=self.PANEL, width=405)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = tk.Frame(body, bg=self.PANEL_DARK)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))

        tk.Label(
            left,
            text="Pipeline operacional",
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            left,
            text=f"{len(SCRIPTS)} processos executados sequencialmente. Em caso de erro, a rotina é interrompida.",
            bg=self.PANEL,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
            wraplength=365,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        steps_wrap = tk.Frame(left, bg=self.PANEL)
        steps_wrap.pack(fill="both", expand=True, padx=16)
        for idx, item in enumerate(SCRIPTS):
            row = tk.Frame(steps_wrap, bg=self.PANEL)
            row.pack(fill="x", pady=3)
            dot = tk.Label(
                row,
                text="●",
                bg=self.PANEL,
                fg=self.INACTIVE,
                font=("Segoe UI", 10, "bold"),
                width=2,
            )
            dot.pack(side="left", anchor="n")
            label = tk.Label(
                row,
                text=f"{idx + 1:02d}. {item['description']}",
                bg=self.PANEL,
                fg=self.TEXT_MUTED,
                font=("Segoe UI", 8),
                wraplength=330,
                justify="left",
                anchor="w",
            )
            label.pack(side="left", fill="x", expand=True)
            self.step_dots.append(dot)
            self.step_labels.append(label)

        info_box = tk.Frame(left, bg=self.CARD_ALT)
        info_box.pack(fill="x", padx=16, pady=16)
        tk.Label(
            info_box,
            text="Escopo da rotina",
            bg=self.CARD_ALT,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(
            info_box,
            text="Atualização centralizada das fontes utilizadas por Informes de Vendas, Margem Bruta, Painel Diário, Quinta do Óleo e Passagens.",
            bg=self.CARD_ALT,
            fg=self.TEXT_SOFT,
            font=("Segoe UI", 9),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12)
        tk.Label(
            info_box,
            text=f"Log: {ARQUIVO_LOG.name}",
            bg=self.CARD_ALT,
            fg=self.TEXT_MUTED,
            font=("Consolas", 8),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(7, 10))

        status_card = tk.Frame(right, bg=self.CARD)
        status_card.pack(fill="x", padx=16, pady=(16, 10))
        tk.Label(
            status_card,
            text="Status da execução",
            bg=self.CARD,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=14)
        tk.Label(
            status_card,
            textvariable=self.detail_var,
            bg=self.CARD,
            fg=self.ACCENT,
            font=("Segoe UI", 10, "bold"),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(4, 12))

        metrics = tk.Frame(right, bg=self.PANEL_DARK)
        metrics.pack(fill="x", padx=16, pady=(0, 10))
        metric_items = [
            ("PROGRESSO", self.progress_text_var, self.TEXT),
            ("PERCENTUAL", self.percent_var, self.ACCENT),
            ("TEMPO MONITORADO", self.timer_var, self.SUCCESS),
        ]
        for index, (title, variable, color) in enumerate(metric_items):
            card = tk.Frame(metrics, bg=self.CARD)
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(metric_items) - 1 else 5),
            )
            metrics.grid_columnconfigure(index, weight=1)
            tk.Label(
                card, text=title, bg=self.CARD, fg=self.TEXT_MUTED, font=("Segoe UI", 8, "bold")
            ).pack(anchor="w", padx=12, pady=(10, 2))
            tk.Label(
                card, textvariable=variable, bg=self.CARD, fg=color, font=("Segoe UI", 18, "bold")
            ).pack(anchor="w", padx=12, pady=(0, 10))

        progress_card = tk.Frame(right, bg=self.CARD)
        progress_card.pack(fill="x", padx=16, pady=(0, 10))
        progress_head = tk.Frame(progress_card, bg=self.CARD)
        progress_head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(
            progress_head,
            text="Processo atual",
            bg=self.CARD,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Label(
            progress_head,
            textvariable=self.current_script_var,
            bg=self.CARD,
            fg=self.TEXT_SOFT,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")
        self.progress = ttk.Progressbar(
            progress_card,
            style="Accent.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate",
            maximum=len(SCRIPTS),
            value=0,
        )
        self.progress.pack(fill="x", padx=14, pady=(0, 12))

        log_card = tk.Frame(right, bg=self.CARD)
        log_card.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        log_head = tk.Frame(log_card, bg=self.CARD)
        log_head.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(
            log_head,
            text="Log operacional",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        tk.Label(
            log_head,
            text="Saída em tempo real",
            bg=self.CARD,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right")

        log_frame = tk.Frame(log_card, bg=self.LOG_BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.log_text = tk.Text(
            log_frame,
            bg=self.LOG_BG,
            fg="#D8DCE5",
            insertbackground=self.TEXT,
            font=("Consolas", 9),
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
            wrap="word",
            state="disabled",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_configure("info", foreground="#D8DCE5")
        self.log_text.tag_configure("success", foreground="#8DE4A3")
        self.log_text.tag_configure("warning", foreground="#F5C96B")
        self.log_text.tag_configure("error", foreground="#FF9294")
        self.log_text.tag_configure("accent", foreground="#FF7A75")

        footer = tk.Frame(self, bg=self.BG)
        footer.pack(fill="x", padx=20, pady=(0, 14))
        tk.Label(
            footer,
            text="Execução sequencial | Interrupção automática em caso de falha",
            bg=self.BG,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        ttk.Button(footer, text="Fechar", command=self._on_close, style="Secondary.TButton").pack(
            side="right"
        )

    # ─── Feedback visual ─────────────────────────────────────────────────
    def _set_badge(self, text, color):
        self.badge_var.set(text)
        self.badge_label.configure(bg=color)

    def _set_step(self, index, state):
        palette = {
            "inactive": (self.INACTIVE, self.TEXT_MUTED),
            "running": (self.ACCENT, self.TEXT),
            "done": (self.SUCCESS, "#C9F4D4"),
            "error": (self.ERROR, "#FFD1D2"),
        }
        dot, text = palette[state]
        self.step_dots[index].configure(fg=dot)
        self.step_labels[index].configure(fg=text)

    def _reset_pipeline(self):
        for i in range(len(SCRIPTS)):
            self._set_step(i, "inactive")
        self.progress.configure(value=0)
        self.progress_text_var.set(f"0 / {len(SCRIPTS)}")
        self.percent_var.set("0%")
        self.timer_var.set("00:00")
        self.current_script_var.set("Nenhum processo em execução")

    def _append_log(self, message, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {message}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ─── Execução do pipeline ───────────────────────────────────────────────
    def start_execution(self):
        if self.running:
            return
        self.running = True
        self.cancel_requested = False
        self.executed_count = 0
        self.started_at = datetime.now()
        self._reset_pipeline()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_var.set("Preparando execução")
        self.detail_var.set("Validando os scripts e os diretórios configurados.")
        self._set_badge("RPA INICIANDO", self.WARNING)
        self._append_log("=" * 78, "accent")
        self._append_log("INÍCIO DO RPA DE ATUALIZAÇÃO DAS FONTES DE DADOS", "accent")
        self._append_log(f"Arquivo de log: {ARQUIVO_LOG}")
        LOGGER.info("=" * 80)
        LOGGER.info("INÍCIO DO RPA DE ATUALIZAÇÃO DAS FONTES DE DADOS")
        LOGGER.info("=" * 80)
        self.worker_thread = threading.Thread(target=self._run_pipeline, daemon=True)
        self.worker_thread.start()

    def _run_pipeline(self):
        for index, info in enumerate(SCRIPTS):
            if self.cancel_requested:
                self.events.put(("cancelled",))
                return
            ok, detail = validate_script(info)
            if not ok:
                LOGGER.error(detail)
                self.events.put(("preflight_error", index, detail))
                return

        self.events.put(("preflight_ok",))
        for index, info in enumerate(SCRIPTS):
            if self.cancel_requested:
                self.events.put(("cancelled",))
                return
            self.events.put(("step_start", index, info))
            success, code, duration, error = self._execute_script(index, info)
            if self.cancel_requested:
                self.events.put(("cancelled",))
                return
            if not success:
                self.events.put(("step_error", index, info, code, duration, error))
                return
            self.events.put(("step_done", index, info, duration))
        self.events.put(("pipeline_done",))

    def _execute_script(self, index, info):
        directory = Path(info["directory"])
        script_path = directory / info["name"]
        start = datetime.now()
        LOGGER.info("-" * 80)
        LOGGER.info("Iniciando processo: %s", info["description"])
        LOGGER.info("Script: %s", script_path)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self.current_process = subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=str(directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            out_thread = threading.Thread(
                target=self._stream_pipe,
                args=(self.current_process.stdout, "stdout", index),
                daemon=True,
            )
            err_thread = threading.Thread(
                target=self._stream_pipe,
                args=(self.current_process.stderr, "stderr", index),
                daemon=True,
            )
            out_thread.start()
            err_thread.start()
            code = self.current_process.wait()
            out_thread.join(timeout=1)
            err_thread.join(timeout=1)
            duration = (datetime.now() - start).total_seconds()
            if self.cancel_requested:
                return False, code, duration, "Execução cancelada pelo usuário."
            if code == 0:
                LOGGER.info("Concluído com sucesso: %s", info["description"])
                LOGGER.info("Tempo de execução: %s", format_duration(duration))
                return True, code, duration, ""
            LOGGER.error("Erro ao executar: %s", info["description"])
            LOGGER.error("Código de retorno: %s", code)
            return False, code, duration, f"O processo terminou com código de retorno {code}."
        except Exception as exc:
            duration = (datetime.now() - start).total_seconds()
            LOGGER.exception("Falha inesperada ao executar %s", info["description"])
            return False, -1, duration, str(exc)
        finally:
            self.current_process = None

    def _stream_pipe(self, pipe, kind, index):
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):
                line = line.rstrip()
                if not line:
                    continue
                LOGGER.info("%s | %s | %s", SCRIPTS[index]["name"], kind.upper(), line)
                self.events.put(("stream", kind, line))
        finally:
            try:
                pipe.close()
            except Exception:
                LOGGER.debug("Falha ao fechar pipe do subprocesso.", exc_info=True)

    def cancel_execution(self):
        if not self.running:
            return
        if not messagebox.askyesno(
            "Interromper execução", "Deseja realmente interromper a rotina em andamento?"
        ):
            return
        self.cancel_requested = True
        self.cancel_button.configure(state="disabled")
        self._set_badge("CANCELANDO", self.WARNING)
        self.status_var.set("Interrompendo execução")
        self.detail_var.set("Aguardando o encerramento seguro do processo atual.")
        self._append_log("Solicitação de cancelamento recebida.", "warning")
        process = self.current_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception as exc:
                LOGGER.exception("Falha ao encerrar processo atual.")
                self._append_log(
                    f"Não foi possível solicitar o encerramento do processo: {exc}", "error"
                )

    # ─── Loop de eventos e atualização da UI ────────────────────────────────
    def _process_events(self):
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_events)

    def _handle_event(self, event):
        kind = event[0]
        if kind == "preflight_ok":
            self.status_var.set("Validação concluída")
            self.detail_var.set("Todos os scripts foram localizados. Iniciando a execução.")
            self._set_badge("RPA EM EXECUÇÃO", self.ACCENT)
            self._append_log("Validação prévia concluída com sucesso.", "success")
        elif kind == "preflight_error":
            _, index, detail = event
            self._set_step(index, "error")
            self.status_var.set("Falha na validação inicial")
            self.detail_var.set(detail)
            self._set_badge("RPA COM ERRO", self.ERROR)
            self._append_log(detail, "error")
            self._finish_running_state()
        elif kind == "step_start":
            _, index, info = event
            self._set_step(index, "running")
            self.status_var.set(f"Executando processo {index + 1} de {len(SCRIPTS)}")
            self.detail_var.set(info["description"])
            self.current_script_var.set(info["name"])
            self._append_log(f"Iniciando: {info['description']}", "accent")
            self._append_log(f"Script: {Path(info['directory']) / info['name']}")
        elif kind == "stream":
            _, stream_kind, line = event
            self._append_log(line, "error" if stream_kind == "stderr" else "info")
        elif kind == "step_done":
            _, index, info, duration = event
            self.executed_count += 1
            self._set_step(index, "done")
            current = index + 1
            percent = round(current / len(SCRIPTS) * 100)
            self.progress.configure(value=current)
            self.progress_text_var.set(f"{current} / {len(SCRIPTS)}")
            self.percent_var.set(f"{percent}%")
            self._append_log(
                f"Concluído com sucesso em {format_duration(duration)}: {info['description']}",
                "success",
            )
        elif kind == "step_error":
            _, index, info, code, duration, error = event
            self._set_step(index, "error")
            self.status_var.set("Rotina interrompida por erro")
            self.detail_var.set(info["description"])
            self._set_badge("RPA COM ERRO", self.ERROR)
            self._append_log(
                f"ERRO em {info['name']} | retorno={code} | tempo={format_duration(duration)}",
                "error",
            )
            if error:
                self._append_log(error, "error")
            LOGGER.error(
                "Rotina interrompida no processo %s/%s: %s",
                index + 1,
                len(SCRIPTS),
                info["description"],
            )
            self._finish_running_state()
        elif kind == "pipeline_done":
            total = (datetime.now() - self.started_at).total_seconds() if self.started_at else 0
            self.progress.configure(value=len(SCRIPTS))
            self.progress_text_var.set(f"{len(SCRIPTS)} / {len(SCRIPTS)}")
            self.percent_var.set("100%")
            self.current_script_var.set("Rotina finalizada")
            self.status_var.set("RPA finalizado com sucesso")
            self.detail_var.set(
                f"{self.executed_count} processos executados em {format_duration(total)}."
            )
            self._set_badge("RPA CONCLUÍDO", self.SUCCESS)
            self._append_log("=" * 78, "success")
            self._append_log("RPA FINALIZADO COM SUCESSO", "success")
            self._append_log(f"Scripts executados: {self.executed_count}/{len(SCRIPTS)}", "success")
            self._append_log(f"Tempo total: {format_duration(total)}", "success")
            LOGGER.info("RPA FINALIZADO COM SUCESSO")
            LOGGER.info("Scripts executados: %s/%s", self.executed_count, len(SCRIPTS))
            LOGGER.info("Tempo total: %s", format_duration(total))
            self._finish_running_state()
        elif kind == "cancelled":
            self.status_var.set("Execução interrompida")
            self.detail_var.set("A rotina foi cancelada pelo usuário.")
            self._set_badge("RPA INTERROMPIDO", self.WARNING)
            self.current_script_var.set("Execução cancelada")
            self._append_log("RPA interrompido pelo usuário.", "warning")
            LOGGER.warning("RPA interrompido pelo usuário.")
            self._finish_running_state()

    def _finish_running_state(self):
        self.running = False
        self.current_process = None
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _update_timer(self):
        if self.running and self.started_at:
            self.timer_var.set(format_duration((datetime.now() - self.started_at).total_seconds()))
        self.after(500, self._update_timer)

    # ─── Ações auxiliares da janela ─────────────────────────────────────────
    def open_log_folder(self):
        try:
            if os.name == "nt":
                os.startfile(LOG_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(LOG_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(LOG_DIR)])
        except Exception as exc:
            messagebox.showerror("Abrir pasta de logs", f"Não foi possível abrir a pasta:\n{exc}")

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno(
                "RPA em execução", "Existe uma rotina em andamento. Deseja interromper e fechar?"
            ):
                return
            self.cancel_requested = True
            process = self.current_process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    LOGGER.debug("Falha ao encerrar processo ao fechar a janela.", exc_info=True)
        self.destroy()


def main() -> None:
    app = RPAFontesApp()
    app.mainloop()


if __name__ == "__main__":
    main()
