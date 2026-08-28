"""Segunda tela: mostra o conteúdo do PDF como campos nativos (não como
imagem), com Responsável, Qtde Chapas Real e Obs editáveis, Comentários embutidos e botão Concluir.
"""
import getpass
import tkinter as tk
from tkinter import messagebox, ttk

from . import store
from .parser import ParseError, parse_pdf
from .preview import PdfPreviewWindow

ERROR_BG = "#ffc9c9"
NORMAL_BG = "white"
HEADER_FONT = ("Segoe UI", 14, "bold")
LOTE_FONT = ("Segoe UI", 11, "bold")
COL_FONT = ("Segoe UI", 9, "bold")
CELL_FONT = ("Segoe UI", 9)


class DetailWindow(tk.Toplevel):
    """Janela de um PDF específico com separação de chapas e comentários embutidos."""

    def __init__(self, parent, root_path: str, pdf_path: str, pdf_stem: str, on_saved=None):
        super().__init__(parent)
        self.root_path = root_path
        self.pdf_path = pdf_path
        self.pdf_stem = pdf_stem
        self.on_saved = on_saved
        self.item_widgets = []  # [(chave, entry_qtde, entry_obs)]

        self.geometry("1000x700")
        self.minsize(800, 520)

        try:
            self.pages = parse_pdf(pdf_path)
        except ParseError as exc:
            messagebox.showerror("Separação Chapas", str(exc), parent=parent)
            self.destroy()
            return

        self.record = store.load_record(root_path, pdf_stem)
        lotes = ", ".join(p.lote for p in self.pages if p.lote)
        self.title(f"Separação Chapas — Lote {lotes}")

        self._sync_timer = None
        self._build_widgets()
        self._fill_from_record()
        self._schedule_comments_sync()

    # ---------- construção da tela ----------

    def _build_widgets(self):
        top = tk.Frame(self, padx=14, pady=10)
        top.pack(fill="x")

        tk.Label(top, text="SEPARAÇÃO CHAPAS", font=HEADER_FONT).pack(side="left")

        resp_frame = tk.Frame(top)
        resp_frame.pack(side="right")

        self.prio_var = tk.BooleanVar(value=False)
        self.prio_check = tk.Checkbutton(
            resp_frame,
            text="⭐ Prioridade",
            variable=self.prio_var,
            font=COL_FONT,
            fg="#c2410c",
            activeforeground="#9a3412",
            command=self._on_prio_toggled,
            cursor="hand2",
        )
        self.prio_check.pack(side="left", padx=(0, 16))

        tk.Label(resp_frame, text="Responsável:", font=COL_FONT).pack(side="left", padx=(0, 4))
        self.resp_entry = tk.Entry(resp_frame, width=28, font=CELL_FONT)
        self.resp_entry.pack(side="left")
        self.resp_entry.bind("<KeyRelease>", lambda e: self.resp_entry.configure(bg=NORMAL_BG))

        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var, fg="#1a7a1a", padx=14).pack(fill="x")

        # Barra inferior de ações
        bottom = tk.Frame(self, padx=14, pady=10)
        bottom.pack(fill="x", side="bottom")

        is_concluido = self.record.get("status") == store.STATUS_CONCLUIDO

        if is_concluido:
            tk.Button(
                bottom, text="Alterar", width=14, font=COL_FONT, command=self._alterar
            ).pack(side="right")
        else:
            tk.Button(
                bottom, text="Concluir", width=14, font=COL_FONT, bg="#d4edda", command=self._concluir
            ).pack(side="right", padx=(8, 0))
            tk.Button(
                bottom, text="Salvar", width=12, command=self._salvar
            ).pack(side="right")

        tk.Button(bottom, text="Ver PDF original", command=self._ver_pdf).pack(side="left")

        emitted = next((p for p in self.pages if p.emitido_por), None)
        if emitted:
            tk.Label(
                bottom,
                text=f"Emitido por {emitted.emitido_por} em {emitted.emitido_em}",
                fg="#666",
            ).pack(side="left", padx=(16, 0))

        # Divisor vertical meio a meio (50% Itens / 50% Comentários)
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=14, pady=(4, 6))

        # Painel Superior: Tabela de Itens (Metade superior)
        items_frame = tk.Frame(paned)
        paned.add(items_frame, weight=1)

        self.canvas = tk.Canvas(items_frame, highlightthickness=0)
        vsb = ttk.Scrollbar(items_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.inner = tk.Frame(self.canvas)
        inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfigure(inner_id, width=e.width)
        )
        self.bind_all("<MouseWheel>", self._on_mousewheel)

        vcmd_digits = (self.register(self._validate_digits), "%P")

        item_index = 0
        for page in self.pages:
            section = tk.Frame(self.inner, pady=6)
            section.pack(fill="x")

            head = tk.Frame(section)
            head.pack(fill="x", pady=(0, 6))
            tk.Label(head, text=f"Lote:  {page.lote}", font=LOTE_FONT).pack(side="left")
            if page.descricao:
                tk.Label(head, text=page.descricao, font=LOTE_FONT, fg="#333").pack(
                    side="left", padx=(30, 0)
                )

            grid = tk.Frame(section)
            grid.pack(fill="x")
            headers = ["Código", "Descrição do Item", "Metros", "Quantidade", "Qtde Chapas Real", "Obs"]
            widths = [12, 42, 8, 10, 16, 28]
            for col, (title, w) in enumerate(zip(headers, widths)):
                tk.Label(grid, text=title, font=COL_FONT, width=w, anchor="w").grid(
                    row=0, column=col, sticky="w", padx=2
                )
            grid.columnconfigure(5, weight=1)

            for r, row in enumerate(page.rows, start=1):
                tk.Label(grid, text=row.codigo, font=CELL_FONT, anchor="w").grid(
                    row=r, column=0, sticky="w", padx=2, pady=2
                )
                tk.Label(grid, text=row.descricao, font=CELL_FONT, anchor="w").grid(
                    row=r, column=1, sticky="w", padx=2
                )
                tk.Label(grid, text=row.metros, font=CELL_FONT, anchor="e", width=8).grid(
                    row=r, column=2, sticky="e", padx=2
                )
                tk.Label(grid, text=row.quantidade, font=CELL_FONT, anchor="e", width=10).grid(
                    row=r, column=3, sticky="e", padx=2
                )
                qtde_entry = tk.Entry(
                    grid,
                    width=16,
                    font=CELL_FONT,
                    justify="center",
                    validate="key",
                    validatecommand=vcmd_digits,
                )
                qtde_entry.grid(row=r, column=4, sticky="w", padx=2)
                qtde_entry.bind("<KeyRelease>", lambda e, entry=qtde_entry: entry.configure(bg=NORMAL_BG))
                obs_entry = tk.Entry(grid, font=CELL_FONT)
                obs_entry.grid(row=r, column=5, sticky="we", padx=2)
                self.item_widgets.append((str(item_index), qtde_entry, obs_entry))
                item_index += 1

        # Painel Inferior: Seção de Comentários (Metade inferior)
        comments_card = tk.LabelFrame(
            paned,
            text=f" 💬 Comentários ({len(self.record.get('comentarios', []))}) ",
            font=COL_FONT,
            padx=10,
            pady=6,
            bg="#f8fafc",
            fg="#0f172a",
        )
        self.comments_card = comments_card
        paned.add(comments_card, weight=1)

        # Linha de inserção de comentário
        input_frame = tk.Frame(comments_card, bg="#f8fafc", pady=4)
        input_frame.pack(fill="x", side="bottom")
        input_frame.columnconfigure(2, weight=1)

        tk.Label(input_frame, text="Autor:", font=COL_FONT, bg="#f8fafc", fg="#334155").grid(
            row=0, column=0, sticky="w", padx=(0, 4)
        )

        default_user = ""
        try:
            default_user = getpass.getuser()
        except Exception:
            default_user = ""

        self.comm_author_entry = tk.Entry(input_frame, font=CELL_FONT, width=16, relief="solid", bd=1)
        self.comm_author_entry.insert(0, default_user)
        self.comm_author_entry.grid(row=0, column=1, sticky="w", padx=(0, 10))

        self.comm_text_entry = tk.Entry(input_frame, font=CELL_FONT, relief="solid", bd=1)
        self.comm_text_entry.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.comm_text_entry.bind("<Return>", lambda e: self._send_comment())

        btn_send_comm = tk.Button(
            input_frame,
            text="Enviar",
            font=COL_FONT,
            bg="#0284c7",
            fg="white",
            activebackground="#0369a1",
            activeforeground="white",
            command=self._send_comment,
            width=10,
            cursor="hand2",
        )
        btn_send_comm.grid(row=0, column=3, sticky="e")

        # Lista de comentários com scroll
        comm_list_container = tk.Frame(comments_card, bg="white", highlightbackground="#cbd5e1", highlightthickness=1)
        comm_list_container.pack(fill="both", expand=True, pady=(0, 4))

        self.comm_canvas = tk.Canvas(comm_list_container, highlightthickness=0, bg="white")
        comm_vsb = ttk.Scrollbar(comm_list_container, orient="vertical", command=self.comm_canvas.yview)
        self.comm_canvas.configure(yscrollcommand=comm_vsb.set)
        self.comm_canvas.pack(side="left", fill="both", expand=True)
        comm_vsb.pack(side="right", fill="y")

        self.comm_inner = tk.Frame(self.comm_canvas, bg="white")
        self.comm_inner_id = self.comm_canvas.create_window((0, 0), window=self.comm_inner, anchor="nw")

        self.comm_inner.bind(
            "<Configure>", lambda e: self.comm_canvas.configure(scrollregion=self.comm_canvas.bbox("all"))
        )
        self.comm_canvas.bind(
            "<Configure>", lambda e: self.comm_canvas.itemconfigure(self.comm_inner_id, width=e.width)
        )

    def _on_mousewheel(self, event):
        if not self.winfo_exists():
            return
        widget = event.widget
        if str(widget).startswith(str(self.comments_card)):
            self.comm_canvas.yview_scroll(int(-event.delta / 120), "units")
        else:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def destroy(self):
        if self._sync_timer:
            try:
                self.after_cancel(self._sync_timer)
            except Exception:
                pass
            self._sync_timer = None
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    def _validate_digits(self, new_val: str) -> bool:
        if new_val == "":
            return True
        return new_val.isdigit() and len(new_val) <= 2

    # ---------- dados ----------

    def _fill_from_record(self):
        self.prio_var.set(bool(self.record.get("prioridade", False)))
        self.resp_entry.insert(0, self.record.get("responsavel", ""))
        itens = self.record.get("itens", {})
        for key, qtde_entry, obs_entry in self.item_widgets:
            saved = itens.get(key, {})
            raw_qtde = str(saved.get("qtde_real", ""))
            clean_qtde = "".join(c for c in raw_qtde if c.isdigit())[:2]
            qtde_entry.insert(0, clean_qtde)
            obs_entry.insert(0, saved.get("obs", ""))
        if self.record.get("status") == store.STATUS_CONCLUIDO:
            self.prio_check.configure(state="disabled")
            who = self.record.get("concluido_por", "")
            when = self.record.get("concluido_em", "")
            self.status_var.set(f"✔ Concluído por {who} em {when}")
        self._load_comments_in_detail()

    def _on_prio_toggled(self):
        new_prio = bool(self.prio_var.get())
        self.record["prioridade"] = new_prio
        try:
            store.save_record(self.root_path, self.pdf_stem, self.record)
        except OSError as exc:
            messagebox.showerror(
                "Prioridade", f"Não foi possível salvar a alteração de prioridade:\n{exc}", parent=self
            )
            return

        if self.on_saved:
            self.on_saved()

    def _salvar(self):
        self.record["prioridade"] = self.prio_var.get()
        self.record["responsavel"] = self.resp_entry.get().strip()
        itens = {}
        for key, qtde_entry, obs_entry in self.item_widgets:
            itens[key] = {"qtde_real": qtde_entry.get().strip(), "obs": obs_entry.get().strip()}
        self.record["itens"] = itens

        try:
            store.save_record(self.root_path, self.pdf_stem, self.record)
        except OSError as exc:
            messagebox.showerror(
                "Salvar", f"Não foi possível salvar na pasta de rede:\n{exc}", parent=self
            )
            return

        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Salvar", "Alterações salvas com sucesso.", parent=self)

    def _alterar(self):
        responsavel = self.resp_entry.get().strip()
        if not responsavel:
            self.resp_entry.configure(bg=ERROR_BG)
            messagebox.showwarning(
                "Alterar", "O campo Responsável não pode ficar vazio.", parent=self
            )
            return

        if not messagebox.askyesno(
            "Confirmar Alteração",
            "Deseja salvar as alterações realizadas neste lote concluído?",
            parent=self,
            icon="question",
        ):
            return

        self.record["prioridade"] = self.prio_var.get()
        self.record["responsavel"] = responsavel
        itens = {}
        for key, qtde_entry, obs_entry in self.item_widgets:
            itens[key] = {"qtde_real": qtde_entry.get().strip(), "obs": obs_entry.get().strip()}
        self.record["itens"] = itens

        try:
            store.save_record(self.root_path, self.pdf_stem, self.record)
        except OSError as exc:
            messagebox.showerror(
                "Alterar", f"Não foi possível salvar na pasta de rede:\n{exc}", parent=self
            )
            return

        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Alterar", "Informações alteradas com sucesso.", parent=self)
        self.destroy()

    def _concluir(self):
        missing = False

        responsavel = self.resp_entry.get().strip()
        if not responsavel:
            self.resp_entry.configure(bg=ERROR_BG)
            missing = True
        else:
            self.resp_entry.configure(bg=NORMAL_BG)

        for _key, qtde_entry, _obs in self.item_widgets:
            if not qtde_entry.get().strip():
                qtde_entry.configure(bg=ERROR_BG)
                missing = True
            else:
                qtde_entry.configure(bg=NORMAL_BG)

        if missing:
            messagebox.showwarning(
                "Concluir",
                "Preencha o Responsável e a Qtde Chapas Real de todos os itens antes de concluir.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Confirmar Conclusão",
            "Tem certeza de que deseja concluir este lote?\n\nO status será alterado para Concluído.",
            parent=self,
            icon="question",
        ):
            return

        self.record["responsavel"] = responsavel
        itens = {}
        for key, qtde_entry, obs_entry in self.item_widgets:
            itens[key] = {"qtde_real": qtde_entry.get().strip(), "obs": obs_entry.get().strip()}
        self.record["itens"] = itens
        store.mark_concluido(self.record)

        try:
            store.save_record(self.root_path, self.pdf_stem, self.record)
        except OSError as exc:
            messagebox.showerror(
                "Concluir", f"Não foi possível salvar na pasta de rede:\n{exc}", parent=self
            )
            return

        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Concluir", "Separação concluída com sucesso.", parent=self)
        self.destroy()

    def _ver_pdf(self):
        PdfPreviewWindow(self, self.pdf_path, title=self.title())

    # ---------- comentários embutidos e sincronização em tempo real ----------

    def _schedule_comments_sync(self):
        self._sync_timer = self.after(1500, self._comments_sync_tick)

    def _comments_sync_tick(self):
        if not self.winfo_exists():
            return
        try:
            latest_record = store.load_record(self.root_path, self.pdf_stem)
            
            # Sincroniza estado de prioridade se mudou remotamente
            latest_prio = bool(latest_record.get("prioridade", False))
            if latest_prio != bool(self.prio_var.get()):
                self.record["prioridade"] = latest_prio
                self.prio_var.set(latest_prio)

            latest_comments = latest_record.get("comentarios", [])
            current_comments = self.record.get("comentarios", [])
            if latest_comments != current_comments:
                had_previous = len(current_comments) > 0
                self.record["comentarios"] = latest_comments
                self._load_comments_in_detail()
                if had_previous and len(latest_comments) > len(current_comments):
                    try:
                        last_comm = latest_comments[-1]
                        current_author = self.comm_author_entry.get().strip()
                        if last_comm.get("autor", "").lower() != current_author.lower():
                            self.bell()
                    except Exception:
                        pass
                if self.on_saved:
                    self.on_saved()
        except Exception:
            pass
        finally:
            self._schedule_comments_sync()

    def _load_comments_in_detail(self):
        for w in self.comm_inner.winfo_children():
            w.destroy()

        comments = self.record.get("comentarios", [])
        self.comments_card.configure(text=f" 💬 Comentários ({len(comments)})  •  🟢 Ao Vivo ")

        if not comments:
            lbl = tk.Label(
                self.comm_inner,
                text="Nenhum comentário registrado ainda para este lote.\nEnvie uma mensagem abaixo.",
                font=("Segoe UI", 9, "italic"),
                fg="#94a3b8",
                bg="white",
                pady=16,
            )
            lbl.pack(fill="x")
            return

        current_author = self.comm_author_entry.get().strip().lower() if hasattr(self, "comm_author_entry") else ""

        for c in comments:
            autor = c.get("autor", "Anônimo")
            data = c.get("data", "")
            texto = c.get("texto", "")

            is_me = bool(current_author) and (autor.lower() == current_author)
            bg_bubble = "#e0f2fe" if is_me else "#f8fafc"
            border_bubble = "#7dd3fc" if is_me else "#e2e8f0"
            autor_fg = "#0284c7" if is_me else "#0369a1"

            bubble = tk.Frame(
                self.comm_inner,
                bg=bg_bubble,
                highlightbackground=border_bubble,
                highlightthickness=1,
                padx=10,
                pady=5,
            )
            bubble.pack(fill="x", pady=3, padx=6)

            top_b = tk.Frame(bubble, bg=bg_bubble)
            top_b.pack(fill="x")

            autor_text = f"👤 {autor} (Você)" if is_me else f"👤 {autor}"
            tk.Label(top_b, text=autor_text, font=("Segoe UI", 9, "bold"), bg=bg_bubble, fg=autor_fg).pack(side="left")
            tk.Label(top_b, text=data, font=("Segoe UI", 8), bg=bg_bubble, fg="#64748b").pack(side="right")

            msg = tk.Label(
                bubble,
                text=texto,
                font=("Segoe UI", 9),
                bg=bg_bubble,
                fg="#0f172a",
                justify="left",
                wraplength=850,
                anchor="w",
            )
            msg.pack(fill="x", pady=(2, 0))

        self.comm_canvas.update_idletasks()
        self.comm_canvas.yview_moveto(1.0)

    def _send_comment(self):
        texto = self.comm_text_entry.get().strip()
        if not texto:
            messagebox.showwarning("Comentários", "Digite uma mensagem antes de enviar.", parent=self)
            return

        autor = self.comm_author_entry.get().strip()
        try:
            store.add_comment(self.root_path, self.pdf_stem, texto=texto, autor=autor)
        except OSError as exc:
            messagebox.showerror("Comentários", f"Não foi possível salvar o comentário:\n{exc}", parent=self)
            return

        self.comm_text_entry.delete(0, "end")
        self.record = store.load_record(self.root_path, self.pdf_stem)
        self._load_comments_in_detail()

        if self.on_saved:
            self.on_saved()
