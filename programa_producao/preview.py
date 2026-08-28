"""Janela de visualização do PDF dentro do próprio programa (sem depender
de um leitor de PDF externo instalado na máquina)."""
import os
import tkinter as tk
from tkinter import messagebox

ZOOM = 1.6  # resolução de renderização das páginas


class PdfPreviewWindow(tk.Toplevel):
    def __init__(self, parent, pdf_path: str, title: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("900x720")
        self.pdf_path = pdf_path
        self._page_images: list[tk.PhotoImage] = []
        self._page_count = 0
        self._current_page = 0

        self._build_widgets()
        self._load_pdf()

    def _build_widgets(self):
        nav = tk.Frame(self, pady=6)
        nav.pack(fill="x")

        self.prev_btn = tk.Button(nav, text="< Anterior", command=self._prev_page, state="disabled")
        self.prev_btn.pack(side="left", padx=8)
        self.next_btn = tk.Button(nav, text="Próxima >", command=self._next_page, state="disabled")
        self.next_btn.pack(side="left")

        self.page_label = tk.Label(nav, text="")
        self.page_label.pack(side="left", padx=12)

        tk.Button(nav, text="Abrir no leitor do Windows", command=self._open_externally).pack(side="right", padx=8)

        canvas_frame = tk.Frame(self)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_frame, background="#808080")
        vsb = tk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        hsb = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.image_item = None

    def _load_pdf(self):
        try:
            import pymupdf as fitz
        except ImportError:
            messagebox.showerror(
                "Visualizar PDF",
                "A biblioteca PyMuPDF não está instalada.\nInstale com: pip install PyMuPDF",
                parent=self,
            )
            self.destroy()
            return

        try:
            doc = fitz.open(self.pdf_path)
            self._page_count = doc.page_count
            matrix = fitz.Matrix(ZOOM, ZOOM)
            for page in doc:
                pix = page.get_pixmap(matrix=matrix)
                photo = tk.PhotoImage(data=pix.tobytes("ppm"))
                self._page_images.append(photo)
            doc.close()
        except Exception as exc:
            messagebox.showerror("Visualizar PDF", f"Não foi possível abrir o PDF:\n{exc}", parent=self)
            self.destroy()
            return

        if not self._page_images:
            messagebox.showwarning("Visualizar PDF", "Este PDF não tem páginas.", parent=self)
            self.destroy()
            return

        self._current_page = 0
        self._show_page(0)
        if self._page_count > 1:
            self.next_btn.configure(state="normal")

    def _show_page(self, index: int):
        photo = self._page_images[index]
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=photo)
        self.canvas.configure(scrollregion=(0, 0, photo.width(), photo.height()))
        self.page_label.configure(text=f"Página {index + 1} de {self._page_count}")
        self.prev_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(state="normal" if index < self._page_count - 1 else "disabled")

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._show_page(self._current_page)

    def _next_page(self):
        if self._current_page < self._page_count - 1:
            self._current_page += 1
            self._show_page(self._current_page)

    def _open_externally(self):
        try:
            os.startfile(self.pdf_path)
        except OSError as exc:
            messagebox.showerror("Abrir no leitor do Windows", f"Não foi possível abrir o arquivo:\n{exc}", parent=self)
