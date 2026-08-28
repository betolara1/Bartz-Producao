"""Módulo de comentários e notificações flutuantes (Toast)."""
import getpass
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from . import store

HEADER_FONT = ("Segoe UI", 12, "bold")
AUTHOR_FONT = ("Segoe UI", 9, "bold")
DATE_FONT = ("Segoe UI", 8)
BODY_FONT = ("Segoe UI", 9)
BTN_FONT = ("Segoe UI", 9, "bold")


class ToastNotification(tk.Toplevel):
    """Notificação flutuante não-bloqueante no canto inferior direito da tela."""

    def __init__(self, parent, title: str, message: str, on_click=None, duration_ms: int = 9000):
        super().__init__(parent)
        self.on_click = on_click
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        bg_color = "#1e293b"
        border_color = "#0284c7"
        text_color = "#f8fafc"

        frame = tk.Frame(self, bg=bg_color, highlightbackground=border_color, highlightthickness=2, padx=12, pady=10)
        frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(frame, bg=bg_color)
        header_frame.pack(fill="x")

        icon_lbl = tk.Label(header_frame, text="🔔", font=("Segoe UI", 12), bg=bg_color, fg="#38bdf8")
        icon_lbl.pack(side="left", padx=(0, 6))

        title_lbl = tk.Label(header_frame, text=title, font=("Segoe UI", 10, "bold"), bg=bg_color, fg="#38bdf8", anchor="w")
        title_lbl.pack(side="left", fill="x", expand=True)

        close_btn = tk.Label(header_frame, text="✕", font=("Segoe UI", 9, "bold"), bg=bg_color, fg="#94a3b8", cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.destroy())

        msg_lbl = tk.Label(frame, text=message, font=BODY_FONT, bg=bg_color, fg=text_color, justify="left", wraplength=280, anchor="w")
        msg_lbl.pack(fill="x", pady=(6, 8))

        if on_click:
            btn_view = tk.Label(frame, text="Visualizar Comentário →", font=("Segoe UI", 8, "bold"), bg=bg_color, fg="#38bdf8", cursor="hand2")
            btn_view.pack(anchor="e")
            for w in (frame, header_frame, icon_lbl, title_lbl, msg_lbl, btn_view):
                w.bind("<Button-1>", self._handle_click)
                w.configure(cursor="hand2")

        self.update_idletasks()
        w = 340
        h = max(100, frame.winfo_reqheight() + 10)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = sw - w - 24
        y = sh - h - 60
        self.geometry(f"{w}x{h}+{x}+{y}")

        try:
            self.bell()
        except Exception:
            pass

        self.after(duration_ms, self._safe_destroy)

    def _handle_click(self, event):
        if self.on_click:
            self.on_click()
        self.destroy()

    def _safe_destroy(self):
        if self.winfo_exists():
            self.destroy()


class CommentsDialog(tk.Toplevel):
    """Janela de histórico e inserção de novos comentários para um PDF/Lote."""

    def __init__(self, parent, root_path: str, pdf_stem: str, lote: str, filename: str, on_comment_added=None):
        super().__init__(parent)
        self.root_path = root_path
        self.pdf_stem = pdf_stem
        self.lote = lote
        self.filename = filename
        self.on_comment_added = on_comment_added

        self.title(f"Comentários — Lote {lote} ({filename})")
        self.geometry("540x520")
        self.minsize(440, 380)
        self.transient(parent)

        self._build_widgets()
        self._load_comments()

    def _build_widgets(self):
        top = tk.Frame(self, padx=14, pady=10, bg="#f1f5f9")
        top.pack(fill="x")

        tk.Label(top, text=f"💬 Comentários — Lote {self.lote}", font=HEADER_FONT, bg="#f1f5f9", fg="#0f172a").pack(side="left")
        tk.Label(top, text=self.filename, font=("Segoe UI", 9), bg="#f1f5f9", fg="#64748b").pack(side="right")

        # Área dos comentários com scroll
        container = tk.Frame(self, padx=14, pady=8)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, highlightthickness=0, bg="white")
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.comments_frame = tk.Frame(self.canvas, bg="white")
        self.inner_id = self.canvas.create_window((0, 0), window=self.comments_frame, anchor="nw")

        self.comments_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(self.inner_id, width=e.width)
        )
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Área de novo comentário
        bottom = tk.Frame(self, padx=14, pady=10, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        bottom.pack(fill="x", side="bottom")

        author_row = tk.Frame(bottom, bg="#f8fafc")
        author_row.pack(fill="x", pady=(0, 6))

        tk.Label(author_row, text="Autor:", font=AUTHOR_FONT, bg="#f8fafc", fg="#334155").pack(side="left", padx=(0, 6))

        default_user = ""
        try:
            default_user = getpass.getuser()
        except Exception:
            default_user = ""

        self.author_entry = tk.Entry(author_row, font=BODY_FONT, width=22, relief="solid", bd=1)
        self.author_entry.insert(0, default_user)
        self.author_entry.pack(side="left")

        tk.Label(author_row, text="Atalho: Ctrl+Enter para enviar", font=("Segoe UI", 8), bg="#f8fafc", fg="#94a3b8").pack(side="right")

        input_row = tk.Frame(bottom, bg="#f8fafc")
        input_row.pack(fill="x")
        input_row.columnconfigure(0, weight=1)
        input_row.rowconfigure(0, weight=1)

        self.txt_comment = tk.Text(
            input_row,
            height=3,
            font=BODY_FONT,
            wrap="word",
            padx=8,
            pady=6,
            relief="solid",
            bd=1,
            highlightthickness=0,
        )
        self.txt_comment.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        def on_ctrl_enter(e):
            self._send_comment()
            return "break"

        self.txt_comment.bind("<Control-Return>", on_ctrl_enter)

        btn_send = tk.Button(
            input_row,
            text="Enviar",
            font=BTN_FONT,
            bg="#0284c7",
            fg="white",
            activebackground="#0369a1",
            activeforeground="white",
            command=self._send_comment,
            width=10,
            cursor="hand2",
            padx=10,
            pady=6,
        )
        btn_send.grid(row=0, column=1, sticky="nsew")

    def _on_mousewheel(self, event):
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _load_comments(self):
        for w in self.comments_frame.winfo_children():
            w.destroy()

        record = store.load_record(self.root_path, self.pdf_stem)
        comments = record.get("comentarios", [])

        if not comments:
            empty_lbl = tk.Label(
                self.comments_frame,
                text="Nenhum comentário registrado ainda para este lote.\nEscreva uma mensagem abaixo.",
                font=("Segoe UI", 9, "italic"),
                fg="#94a3b8",
                bg="white",
                pady=40,
            )
            empty_lbl.pack(fill="x")
            return

        for c in comments:
            autor = c.get("autor", "Anônimo")
            data = c.get("data", "")
            texto = c.get("texto", "")

            bubble = tk.Frame(
                self.comments_frame,
                bg="#f8fafc",
                highlightbackground="#cbd5e1",
                highlightthickness=1,
                padx=10,
                pady=6,
            )
            bubble.pack(fill="x", pady=4, padx=4)

            top_b = tk.Frame(bubble, bg="#f8fafc")
            top_b.pack(fill="x")

            tk.Label(top_b, text=f"👤 {autor}", font=AUTHOR_FONT, bg="#f8fafc", fg="#0369a1").pack(side="left")
            tk.Label(top_b, text=data, font=DATE_FONT, bg="#f8fafc", fg="#64748b").pack(side="right")

            msg = tk.Label(
                bubble,
                text=texto,
                font=BODY_FONT,
                bg="#f8fafc",
                fg="#1e293b",
                justify="left",
                wraplength=460,
                anchor="w",
            )
            msg.pack(fill="x", pady=(4, 0))

        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def _send_comment(self):
        texto = self.txt_comment.get("1.0", "end").strip()
        if not texto:
            messagebox.showwarning("Comentários", "Digite uma mensagem antes de enviar.", parent=self)
            return

        autor = self.author_entry.get().strip()
        try:
            store.add_comment(self.root_path, self.pdf_stem, texto=texto, autor=autor)
        except OSError as exc:
            messagebox.showerror("Comentários", f"Não foi possível salvar o comentário:\n{exc}", parent=self)
            return

        self.txt_comment.delete("1.0", "end")
        self._load_comments()

        if self.on_comment_added:
            self.on_comment_added()
