"""Interface gráfica: lista os PDFs de plano de corte encontrados na pasta de rede."""
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import config as cfg_module
from . import store
from .comments import ToastNotification
from .detail import DetailWindow
from .scanner import PdfEntry, ScanError, scan_pdfs

POLL_MS = 200


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, current_path: str, on_save):
        super().__init__(parent)
        self.title("Configurações")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save

        tk.Label(self, text="Pasta de rede com os PDFs (ex: \\\\pc-henrique\\DXF):").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2)
        )
        self.path_var = tk.StringVar(value=current_path)
        entry = tk.Entry(self, textvariable=self.path_var, width=55)
        entry.grid(row=1, column=0, sticky="we", padx=(10, 4))
        entry.focus_set()
        entry.icursor(tk.END)
        tk.Button(self, text="Procurar...", command=self._browse).grid(row=1, column=1, sticky="w", padx=(0, 10))

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="Salvar", width=12, command=self._save).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancelar", width=12, command=self.destroy).pack(side="left", padx=5)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _browse(self):
        initial = self.path_var.get().strip() or None
        chosen = filedialog.askdirectory(parent=self, title="Selecione a pasta com os PDFs", initialdir=initial)
        if chosen:
            self.path_var.set(chosen)

    def _save(self):
        new_path = self.path_var.get().strip()
        if not new_path:
            messagebox.showwarning("Configurações", "Informe um caminho válido.", parent=self)
            return
        self.on_save(new_path)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Programa Produção — Planos de Corte")
        self.geometry("980x560")
        self.minsize(700, 400)

        self.cfg = cfg_module.load_config()
        if self.cfg.get("window_geometry"):
            try:
                self.geometry(self.cfg["window_geometry"])
            except tk.TclError:
                pass

        self.all_entries: list[PdfEntry] = []
        self.records: dict = {}
        self.pending_order: list[str] = []
        self.known_paths: set[str] = set()
        self.known_comment_ids: set[str] = set()
        self.seen_comment_ids: set[str] = set(self.cfg.get("seen_comment_ids", []))
        self.unread_comment_paths: set[str] = set()
        self._is_first_scan = True
        self.result_queue: "queue.Queue" = queue.Queue()
        self.scanning = False

        self._sort_key = "ordem"
        self._sort_reverse = False

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(100, self.request_scan)
        self.after(POLL_MS, self._poll_queue)
        self._schedule_auto_refresh()

    def _build_widgets(self):
        top = tk.Frame(self, padx=10, pady=8)
        top.pack(fill="x")

        tk.Label(top, text="Buscar por lote:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = tk.Entry(top, textvariable=self.search_var, width=20)
        search_entry.pack(side="left", padx=(4, 16))

        tk.Button(top, text="Atualizar agora", command=self.request_scan).pack(side="left")
        tk.Button(top, text="Configurações...", command=self._open_settings).pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="")
        tk.Label(top, textvariable=self.status_var, anchor="e").pack(side="right")

        columns = ("ordem", "lote", "status", "comentarios", "resp", "arquivo", "modificado", "tamanho")
        headers = {
            "ordem": "Ordem",
            "lote": "Lote",
            "status": "Status",
            "comentarios": "Comentários",
            "resp": "Responsável",
            "arquivo": "Arquivo",
            "modificado": "Modificado em",
            "tamanho": "Tamanho",
        }
        widths = {
            "ordem": 65,
            "lote": 85,
            "status": 105,
            "comentarios": 120,
            "resp": 150,
            "arquivo": 180,
            "modificado": 135,
            "tamanho": 75,
        }

        # Garante suporte a background de tags no Treeview (bug do Tkinter no Windows)
        style = ttk.Style(self)
        def fixed_map(option):
            return [elm for elm in style.map("Treeview", query_opt=option) if elm[:2] != ("!disabled", "!selected")]
        style.map("Treeview", foreground=fixed_map("foreground"), background=fixed_map("background"))

        notebook_frame = tk.Frame(self, padx=10)
        notebook_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.tab_pendentes = tk.Frame(self.notebook)
        self.tab_concluidos = tk.Frame(self.notebook)

        self.notebook.add(self.tab_pendentes, text="Pendentes")
        self.notebook.add(self.tab_concluidos, text="Concluídos")

        def build_tree(parent):
            tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
            for col in columns:
                tree.heading(col, text=headers[col], command=lambda c=col: self._sort_by(c))
                align = "center" if col == "ordem" else "w"
                tree.column(col, width=widths[col], anchor=align)
            tree.tag_configure("prioridade", background="#fed7aa", foreground="#7c2d12")
            tree.tag_configure("pendente", background="#fff3cd", foreground="#000000")
            tree.tag_configure("concluido", background="#d4edda", foreground="#000000")

            vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            tree.bind("<Double-1>", lambda e, t=tree: self._on_tree_double_click(e, t))
            tree.bind("<Return>", lambda e: self._open_selected())
            return tree

        self.tree_pendentes = build_tree(self.tab_pendentes)
        self.tree_concluidos = build_tree(self.tab_concluidos)

        # Atalhos de teclado para movimentação rápida na aba de Pendentes
        self.tree_pendentes.bind("<Alt-Up>", lambda e: (self._move_selected_up(), "break")[1])
        self.tree_pendentes.bind("<Alt-Down>", lambda e: (self._move_selected_down(), "break")[1])
        self.tree_pendentes.bind("<Control-Up>", lambda e: (self._move_selected_up(), "break")[1])
        self.tree_pendentes.bind("<Control-Down>", lambda e: (self._move_selected_down(), "break")[1])
        self.tree_pendentes.bind("<Control-Home>", lambda e: (self._move_selected_top(), "break")[1])

        def show_context_menu(event, tree):
            iid = tree.identify_row(event.y)
            if iid:
                tree.selection_set(iid)
                tree.focus(iid)
                entry = self._selected_entry()
                if entry:
                    menu = tk.Menu(self, tearoff=0)
                    record = self._record_for(entry)
                    if record.get("status") != store.STATUS_CONCLUIDO:
                        if record.get("prioridade"):
                            menu.add_command(label="Remover Prioridade", command=self._toggle_selected_priority)
                        else:
                            menu.add_command(label="⭐ Definir como Prioridade", command=self._toggle_selected_priority)
                        menu.add_separator()
                        menu.add_command(label="▲ Mover para Cima", command=self._move_selected_up)
                        menu.add_command(label="▼ Mover para Baixo", command=self._move_selected_down)
                        menu.add_command(label="⤒ Enviar ao Topo", command=self._move_selected_top)
                        menu.add_separator()
                    menu.add_command(label="Abrir", command=self._open_selected)
                    menu.tk_popup(event.x_root, event.y_root)

        self.tree_pendentes.bind("<Button-3>", lambda e: show_context_menu(e, self.tree_pendentes))
        self.tree_concluidos.bind("<Button-3>", lambda e: show_context_menu(e, self.tree_concluidos))

        bottom = tk.Frame(self, padx=10, pady=8)
        bottom.pack(fill="x")
        tk.Button(bottom, text="Abrir", command=self._open_selected).pack(side="left")
        tk.Button(bottom, text="⭐ Alternar Prioridade", command=self._toggle_selected_priority).pack(side="left", padx=(8, 0))

        # Botões de reordenação da fila de produção (Pendentes)
        tk.Frame(bottom, width=15).pack(side="left")
        self.btn_move_up = tk.Button(bottom, text="▲ Mover para Cima", command=self._move_selected_up)
        self.btn_move_up.pack(side="left", padx=(4, 0))
        self.btn_move_down = tk.Button(bottom, text="▼ Mover para Baixo", command=self._move_selected_down)
        self.btn_move_down.pack(side="left", padx=(4, 0))
        self.btn_move_top = tk.Button(bottom, text="⤒ Enviar ao Topo", command=self._move_selected_top)
        self.btn_move_top.pack(side="left", padx=(4, 0))

    # ---------- scanning ----------

    def request_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.status_var.set(f"Buscando em {self.cfg['root_path']} ...")
        thread = threading.Thread(target=self._scan_worker, args=(self.cfg["root_path"],), daemon=True)
        thread.start()

    def _scan_worker(self, root_path: str):
        try:
            entries = scan_pdfs(root_path)
            records = {
                e.full_path: store.load_record(root_path, Path(e.full_path).stem)
                for e in entries
            }
            saved_order = store.load_pending_order(root_path)
            self.result_queue.put(("ok", (entries, records, saved_order)))
        except ScanError as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "ok":
                    self._on_scan_success(payload)
                else:
                    self._on_scan_error(payload)
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll_queue)

    def _on_scan_success(self, payload):
        entries, records, saved_order = payload
        self.scanning = False
        new_paths = {e.full_path for e in entries}
        newly_found = new_paths - self.known_paths if self.known_paths else set()
        self.known_paths = new_paths
        self.all_entries = entries
        self.records = records
        self._newly_found = newly_found

        self._sync_pending_order(entries, records, saved_order)

        import getpass
        current_user = ""
        try:
            current_user = getpass.getuser().lower().strip()
        except Exception:
            pass

        new_comments_found = []
        for e in entries:
            record = records.get(e.full_path, {})
            comms = record.get("comentarios", [])
            for c in comms:
                cid = c.get("id") or f"{e.full_path}_{c.get('data')}_{c.get('texto')}"
                author = c.get("autor", "").lower().strip()
                is_from_me = bool(current_user and author == current_user)

                if not self._is_first_scan:
                    if cid not in self.known_comment_ids:
                        if not is_from_me:
                            new_comments_found.append((e, c))
                            self.unread_comment_paths.add(e.full_path)
                        else:
                            self.seen_comment_ids.add(cid)
                else:
                    if self.seen_comment_ids and cid not in self.seen_comment_ids and not is_from_me:
                        self.unread_comment_paths.add(e.full_path)

                self.known_comment_ids.add(cid)

        if self._is_first_scan:
            if not self.seen_comment_ids:
                self.seen_comment_ids = set(self.known_comment_ids)
                self._save_seen_comments()

        self._is_first_scan = False

        self._apply_filter()
        from datetime import datetime

        now = datetime.now().strftime("%H:%M:%S")
        self.status_var.set(f"{len(entries)} PDF(s) encontrados — última busca às {now}")

        if new_comments_found:
            for entry_item, comment_item in new_comments_found[-3:]:
                autor = comment_item.get("autor", "Alguém")
                texto = comment_item.get("texto", "")
                is_done = self._record_for(entry_item).get("status") == store.STATUS_CONCLUIDO
                aba_nome = "Concluídos" if is_done else "Pendentes"
                title = f"💬 Nova Mensagem — Lote {entry_item.lote} [{aba_nome}]"
                msg = f"{autor}: \"{texto}\""
                ToastNotification(
                    self,
                    title=title,
                    message=msg,
                    on_click=lambda ent=entry_item: self._open_comments(ent),
                )

    def _sync_pending_order(self, entries: list[PdfEntry], records: dict, saved_order: list[str]):
        pending_entries = [
            e for e in entries
            if records.get(e.full_path, {}).get("status") != store.STATUS_CONCLUIDO
        ]
        pending_filenames = {e.filename for e in pending_entries}

        # Preserva os itens que estão na ordem salva e ainda existem como pendentes
        consolidated = [fn for fn in saved_order if fn in pending_filenames]
        existing_set = set(consolidated)

        # Identifica novos pendentes que ainda não constam na ordem salva
        new_entries = [e for e in pending_entries if e.filename not in existing_set]

        if not consolidated and new_entries:
            # Primeira carga: prioridades primeiro, depois mais recentes
            initial_sorted = self._initial_order(new_entries)
            consolidated = [e.filename for e in initial_sorted]
            try:
                store.save_pending_order(self.cfg["root_path"], consolidated)
            except OSError:
                pass
        elif new_entries:
            # Novos arquivos chegados na pasta: anexa ao final da fila existente
            sorted_new = self._initial_order(new_entries)
            for e in sorted_new:
                consolidated.append(e.filename)
            try:
                store.save_pending_order(self.cfg["root_path"], consolidated)
            except OSError:
                pass

        self.pending_order = consolidated

    def _initial_order(self, entries: list[PdfEntry]) -> list[PdfEntry]:
        priority = [e for e in entries if self._is_priority(e)]
        regular = [e for e in entries if not self._is_priority(e)]
        return sorted(priority, key=lambda e: e.mtime, reverse=True) + sorted(regular, key=lambda e: e.mtime, reverse=True)

    def _save_seen_comments(self):
        try:
            self.cfg["seen_comment_ids"] = list(self.seen_comment_ids)[-500:]
            cfg_module.save_config(self.cfg)
        except Exception:
            pass

    def _on_scan_error(self, message: str):
        self.scanning = False
        self.status_var.set(message)

    def _schedule_auto_refresh(self):
        interval_ms = max(5, int(self.cfg.get("refresh_seconds", 30))) * 100
        self.after(interval_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.request_scan()
        self._schedule_auto_refresh()

    # ---------- filtering / sorting / display ----------

    def _apply_filter(self):
        term = self.search_var.get().strip().lower()
        filtered = [e for e in self.all_entries if term in e.lote.lower()] if term else list(self.all_entries)
        filtered = self._sorted(filtered)
        self._render(filtered)

    def _is_priority(self, entry: PdfEntry) -> bool:
        record = self._record_for(entry)
        return bool(record.get("prioridade", False) and record.get("status") != store.STATUS_CONCLUIDO)

    def _comments_text(self, entry: PdfEntry) -> str:
        record = self._record_for(entry)
        comms = record.get("comentarios", [])
        count = len(comms)
        if entry.full_path in self.unread_comment_paths:
            return f"💬 {count or 1} 🔴 Nova!"
        if not comms:
            return "—"
        return f"💬 {count}"

    def _order_display_rank(self, entry: PdfEntry) -> int:
        record = self._record_for(entry)
        if record.get("status") == store.STATUS_CONCLUIDO:
            return 999999
        try:
            return self.pending_order.index(entry.filename) + 1
        except ValueError:
            return 99999

    def _sorted(self, entries: list[PdfEntry]) -> list[PdfEntry]:
        if self._sort_key == "ordem":
            pending = [e for e in entries if self._record_for(e).get("status") != store.STATUS_CONCLUIDO]
            concluded = [e for e in entries if self._record_for(e).get("status") == store.STATUS_CONCLUIDO]

            sorted_pending = sorted(pending, key=lambda e: self._order_display_rank(e), reverse=self._sort_reverse)
            sorted_concluded = sorted(concluded, key=lambda e: e.mtime, reverse=True)
            return sorted_pending + sorted_concluded

        key_map = {
            "ordem": lambda e: self._order_display_rank(e),
            "lote": lambda e: e.lote,
            "status": lambda e: self._status_text(e),
            "comentarios": lambda e: len(self._record_for(e).get("comentarios", [])),
            "resp": lambda e: self._record_for(e).get("responsavel", "").lower(),
            "arquivo": lambda e: e.filename.lower(),
            "modificado": lambda e: e.mtime,
            "tamanho": lambda e: e.size,
        }
        key_fn = key_map.get(self._sort_key, key_map["modificado"])

        priority_entries = [e for e in entries if self._is_priority(e)]
        regular_entries = [e for e in entries if not self._is_priority(e)]

        sorted_priority = sorted(priority_entries, key=key_fn, reverse=self._sort_reverse)
        sorted_regular = sorted(regular_entries, key=key_fn, reverse=self._sort_reverse)

        return sorted_priority + sorted_regular

    def _sort_by(self, column: str):
        if self._sort_key == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = column
            self._sort_reverse = False
        self._apply_filter()

    def _record_for(self, entry: PdfEntry) -> dict:
        return self.records.get(entry.full_path, store.empty_record())

    def _status_text(self, entry: PdfEntry) -> str:
        record = self._record_for(entry)
        if record.get("status") == store.STATUS_CONCLUIDO:
            return "Concluído"
        if record.get("prioridade"):
            return "⭐ Prioridade"
        return "Pendente"

    def _active_tree(self) -> ttk.Treeview:
        try:
            current = self.notebook.index(self.notebook.select())
            return self.tree_concluidos if current == 1 else self.tree_pendentes
        except Exception:
            return self.tree_pendentes

    def _sync_tree(
        self,
        tree: ttk.Treeview,
        rows: list[tuple[str, tuple, tuple]],
        target_selection: set[str],
    ):
        existing_items = list(tree.get_children())
        existing_set = set(existing_items)
        target_iids = [r[0] for r in rows]
        target_set = set(target_iids)

        # 1. Remover itens que não existem mais
        for iid in existing_items:
            if iid not in target_set:
                tree.delete(iid)

        # 2. Inserir ou atualizar itens existentes e garantir a ordem correta
        for idx, (iid, values, tags) in enumerate(rows):
            if iid in existing_set:
                cur_values = tree.item(iid, "values")
                cur_tags = tree.item(iid, "tags")
                if tuple(str(v) for v in values) != tuple(str(v) for v in cur_values) or tuple(tags) != tuple(cur_tags):
                    tree.item(iid, values=values, tags=tags)
                if tree.index(iid) != idx:
                    tree.move(iid, "", idx)
            else:
                tree.insert("", idx, iid=iid, values=values, tags=tags)

        # 3. Manter / restaurar seleção se o item existir na árvore
        valid_selection = [iid for iid in target_selection if tree.exists(iid)]
        if valid_selection:
            current_sel = set(tree.selection())
            if set(valid_selection) != current_sel:
                tree.selection_set(valid_selection)
            if not tree.focus() or not tree.exists(tree.focus()):
                tree.focus(valid_selection[0])

    def _render(self, entries: list[PdfEntry]):
        sel_pendentes = set(self.tree_pendentes.selection())
        sel_concluidos = set(self.tree_concluidos.selection())

        rows_pendentes: list[tuple[str, tuple, tuple]] = []
        rows_concluidos: list[tuple[str, tuple, tuple]] = []

        for entry in entries:
            record = self._record_for(entry)
            is_done = record.get("status") == store.STATUS_CONCLUIDO
            if is_done:
                ordem_str = "—"
            else:
                try:
                    pos = self.pending_order.index(entry.filename) + 1
                    ordem_str = f"{pos}º"
                except ValueError:
                    ordem_str = "—"

            vals = (
                ordem_str,
                entry.lote,
                self._status_text(entry),
                self._comments_text(entry),
                record.get("responsavel", ""),
                entry.filename,
                entry.modified_str,
                entry.size_str,
            )
            if is_done:
                rows_concluidos.append((entry.full_path, vals, ("concluido",)))
            else:
                is_prio = bool(record.get("prioridade", False))
                tags = ("prioridade",) if is_prio else ("pendente",)
                rows_pendentes.append((entry.full_path, vals, tags))

        target_sel_pendentes = set(sel_pendentes)
        target_sel_concluidos = set(sel_concluidos)

        # Se um item selecionado mudou de aba, mantém ele selecionado na nova aba
        for iid in sel_concluidos:
            if any(r[0] == iid for r in rows_pendentes):
                target_sel_pendentes.add(iid)
        for iid in sel_pendentes:
            if any(r[0] == iid for r in rows_concluidos):
                target_sel_concluidos.add(iid)

        self._sync_tree(self.tree_pendentes, rows_pendentes, target_sel_pendentes)
        self._sync_tree(self.tree_concluidos, rows_concluidos, target_sel_concluidos)

        unread_pendentes = sum(
            1 for e in self.all_entries
            if e.full_path in self.unread_comment_paths
            and self._record_for(e).get("status") != store.STATUS_CONCLUIDO
        )
        unread_concluidos = sum(
            1 for e in self.all_entries
            if e.full_path in self.unread_comment_paths
            and self._record_for(e).get("status") == store.STATUS_CONCLUIDO
        )

        tab_pend_text = f"Pendentes ({len(rows_pendentes)})"
        if unread_pendentes > 0:
            tab_pend_text += f" 💬 🔴 ({unread_pendentes} nova{'s' if unread_pendentes > 1 else ''})"

        tab_conc_text = f"Concluídos ({len(rows_concluidos)})"
        if unread_concluidos > 0:
            tab_conc_text += f" 💬 🔴 ({unread_concluidos} nova{'s' if unread_concluidos > 1 else ''})"

        self.notebook.tab(0, text=tab_pend_text)
        self.notebook.tab(1, text=tab_conc_text)

    # ---------- actions ----------

    def _on_tab_changed(self, event=None):
        btn_up = getattr(self, "btn_move_up", None)
        btn_down = getattr(self, "btn_move_down", None)
        btn_top = getattr(self, "btn_move_top", None)
        if btn_up and btn_down and btn_top:
            try:
                is_pendentes = (self.notebook.index(self.notebook.select()) == 0)
                state = "normal" if is_pendentes else "disabled"
                btn_up.config(state=state)
                btn_down.config(state=state)
                btn_top.config(state=state)
            except Exception:
                pass

    def _move_selected(self, direction: str):
        if self._active_tree() != self.tree_pendentes:
            messagebox.showinfo("Ordem de Produção", "Apenas lotes pendentes podem ser reordenados na fila.")
            return

        entry = self._selected_entry()
        if not entry:
            messagebox.showinfo("Ordem de Produção", "Selecione um lote pendente para mover.")
            return

        # Garante que a visualização esteja ordenada pela fila para o movimento ser visível imediatamente
        if self._sort_key != "ordem" or self._sort_reverse:
            self._sort_key = "ordem"
            self._sort_reverse = False

        term = self.search_var.get().strip().lower()
        visible_entries = [
            e for e in self.all_entries
            if self._record_for(e).get("status") != store.STATUS_CONCLUIDO
            and (not term or term in e.lote.lower())
        ]
        visible_entries.sort(key=lambda e: self._order_display_rank(e))

        visible_filenames = [e.filename for e in visible_entries]
        if entry.filename not in visible_filenames:
            return

        idx = visible_filenames.index(entry.filename)

        if direction == "up":
            if idx == 0:
                self.bell()
                return
            target_fn = visible_filenames[idx - 1]
            if entry.filename in self.pending_order and target_fn in self.pending_order:
                self.pending_order.remove(entry.filename)
                target_idx = self.pending_order.index(target_fn)
                self.pending_order.insert(target_idx, entry.filename)
        elif direction == "down":
            if idx >= len(visible_filenames) - 1:
                self.bell()
                return
            target_fn = visible_filenames[idx + 1]
            if entry.filename in self.pending_order and target_fn in self.pending_order:
                self.pending_order.remove(entry.filename)
                target_idx = self.pending_order.index(target_fn)
                self.pending_order.insert(target_idx + 1, entry.filename)
        elif direction == "top":
            if idx == 0:
                self.bell()
                return
            if entry.filename in self.pending_order:
                self.pending_order.remove(entry.filename)
                self.pending_order.insert(0, entry.filename)

        try:
            store.save_pending_order(self.cfg["root_path"], self.pending_order)
        except OSError as exc:
            messagebox.showwarning("Aviso", f"Ordem alterada localmente, mas houve erro ao salvar na rede:\n{exc}")

        self._apply_filter()

        if self.tree_pendentes.exists(entry.full_path):
            self.tree_pendentes.selection_set(entry.full_path)
            self.tree_pendentes.focus(entry.full_path)
            self.tree_pendentes.see(entry.full_path)

    def _move_selected_up(self):
        self._move_selected("up")

    def _move_selected_down(self):
        self._move_selected("down")

    def _move_selected_top(self):
        self._move_selected("top")

    def _on_tree_double_click(self, event, tree: ttk.Treeview):
        iid = tree.identify_row(event.y)
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
            entry = next((e for e in self.all_entries if e.full_path == iid), None)
            if entry:
                self._open_selected(target_entry=entry)
                return
        self._open_selected()

    def _mark_comments_read(self, entry: PdfEntry):
        if entry.full_path in self.unread_comment_paths:
            self.unread_comment_paths.discard(entry.full_path)
            record = self._record_for(entry)
            for c in record.get("comentarios", []):
                cid = c.get("id") or f"{entry.full_path}_{c.get('data')}_{c.get('texto')}"
                self.seen_comment_ids.add(cid)
            self._save_seen_comments()
            self._apply_filter()

    def _open_comments(self, target_entry: "PdfEntry | None" = None):
        entry = target_entry or self._selected_entry()
        if not entry:
            messagebox.showinfo("Comentários", "Selecione um item na lista primeiro.")
            return

        is_done = self._record_for(entry).get("status") == store.STATUS_CONCLUIDO
        if is_done:
            self.notebook.select(self.tab_concluidos)
            target_tree = self.tree_concluidos
        else:
            self.notebook.select(self.tab_pendentes)
            target_tree = self.tree_pendentes

        if target_tree.exists(entry.full_path):
            target_tree.selection_set(entry.full_path)
            target_tree.focus(entry.full_path)
            target_tree.see(entry.full_path)

        self._mark_comments_read(entry)

        DetailWindow(
            self,
            root_path=self.cfg["root_path"],
            pdf_path=entry.full_path,
            pdf_stem=Path(entry.full_path).stem,
            on_saved=self.request_scan,
        )

    def _toggle_selected_priority(self):
        entry = self._selected_entry()
        if not entry:
            messagebox.showinfo("Prioridade", "Selecione um item na lista primeiro.")
            return
        record = self._record_for(entry)
        if record.get("status") == store.STATUS_CONCLUIDO:
            messagebox.showinfo("Prioridade", "Lotes já concluídos não podem ser marcados como prioridade.")
            return

        pdf_stem = Path(entry.full_path).stem
        new_state = not record.get("prioridade", False)
        record["prioridade"] = new_state
        try:
            store.save_record(self.cfg["root_path"], pdf_stem, record)
        except OSError as exc:
            messagebox.showerror("Prioridade", f"Não foi possível salvar na pasta de rede:\n{exc}")
            return

        self.records[entry.full_path] = record

        # Se virou prioridade, move para o topo da fila de produção pendente
        if new_state and entry.filename in self.pending_order:
            self.pending_order.remove(entry.filename)
            self.pending_order.insert(0, entry.filename)
            try:
                store.save_pending_order(self.cfg["root_path"], self.pending_order)
            except OSError:
                pass

        self._apply_filter()

    def _selected_entry(self) -> "PdfEntry | None":
        tree = self._active_tree()
        selection = tree.selection()
        if not selection:
            return None
        full_path = selection[0]
        for entry in self.all_entries:
            if entry.full_path == full_path:
                return entry
        return None

    def _open_selected(self, target_entry: "PdfEntry | None" = None):
        entry = target_entry or self._selected_entry()
        if not entry:
            messagebox.showinfo("Abrir", "Selecione um item na lista primeiro.")
            return

        self._mark_comments_read(entry)

        DetailWindow(
            self,
            root_path=self.cfg["root_path"],
            pdf_path=entry.full_path,
            pdf_stem=Path(entry.full_path).stem,
            on_saved=self.request_scan,
        )

    def _open_settings(self):
        def on_save(new_path: str):
            self.cfg["root_path"] = new_path
            cfg_module.save_config(self.cfg)
            self.request_scan()

        SettingsDialog(self, self.cfg["root_path"], on_save)

    def _on_close(self):
        self.cfg["window_geometry"] = self.geometry()
        cfg_module.save_config(self.cfg)
        self.destroy()


def main():
    app = App()
    app.mainloop()
