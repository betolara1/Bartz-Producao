"""Varredura da pasta de rede em busca dos PDFs de plano de corte."""
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Evita renomear um arquivo que a impressora PDF ainda esteja gravando.
MIN_AGE_SECONDS = 5

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')

LOTE_IN_NAME = re.compile(r"lote[\s\-_]*([\d.,]+)", re.IGNORECASE)
DIGITS = re.compile(r"[\d.,]+")

# Evita reabrir/reprocessar o texto de PDFs já vistos numa varredura anterior.
_text_lote_cache: dict[tuple[str, float], "str | None"] = {}


def _extract_lote_from_pdf_text(pdf_path: Path) -> "str | None":
    """Extrai o(s) lote(s) do conteúdo do PDF usando o parser por coordenadas
    (o mesmo da tela de detalhe), que funciona na ordem embaralhada em que o
    ERP desenha o texto. PDFs com mais de um lote viram "3399,3407"."""
    try:
        from .parser import parse_pdf
    except ImportError:
        return None
    try:
        pages = parse_pdf(str(pdf_path))
    except Exception:
        # PDFs corrompidos, sem texto ou de outro layout não devem derrubar
        # a varredura inteira — apenas cai no fallback pelo nome do arquivo.
        return None
    lotes = []
    for page in pages:
        if page.lote and page.lote not in lotes:
            lotes.append(page.lote)
    return ",".join(lotes) or None


def _cached_lote_from_text(pdf_path: Path, mtime: float) -> "str | None":
    key = (str(pdf_path), mtime)
    if key not in _text_lote_cache:
        _text_lote_cache[key] = _extract_lote_from_pdf_text(pdf_path)
    return _text_lote_cache[key]


def _prune_text_cache(valid_keys: set) -> None:
    for key in list(_text_lote_cache):
        if key not in valid_keys:
            del _text_lote_cache[key]


@dataclass(frozen=True)
class PdfEntry:
    lote: str
    filename: str
    folder: str
    full_path: str
    mtime: float
    size: int

    @property
    def modified_str(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%d/%m/%Y %H:%M")

    @property
    def size_str(self) -> str:
        kb = self.size / 1024
        if kb < 1024:
            return f"{kb:.0f} KB"
        return f"{kb / 1024:.1f} MB"


def _safe_lote_basename(lote: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", lote).strip()
    return cleaned or "lote"


def _unique_target(folder: Path, lote: str, current: Path) -> Path:
    base = _safe_lote_basename(lote)
    candidate = folder / f"{base}.pdf"
    if candidate == current or not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = folder / f"{base}_{n}.pdf"
        if candidate == current or not candidate.exists():
            return candidate
        n += 1


def _rename_to_lote(pdf_path: Path, lote: str) -> Path:
    """Renomeia o PDF para <lote>.pdf na mesma pasta, evitando colisão de
    nomes. Se o arquivo já estiver com esse nome, ou se o rename falhar
    (arquivo em uso, sem permissão, etc.), devolve o caminho original."""
    if pdf_path.stem == _safe_lote_basename(lote):
        return pdf_path
    target = _unique_target(pdf_path.parent, lote, pdf_path)
    if target == pdf_path:
        return pdf_path
    try:
        pdf_path.rename(target)
        return target
    except OSError:
        return pdf_path


def extract_lote(pdf_path: Path) -> str:
    """Extrai o número do lote a partir do nome da pasta ou do arquivo."""
    for candidate in (pdf_path.parent.name, pdf_path.stem):
        match = LOTE_IN_NAME.search(candidate)
        if match:
            return match.group(1)
    for candidate in (pdf_path.parent.name, pdf_path.stem):
        match = DIGITS.search(candidate)
        if match:
            return match.group(0)
    return pdf_path.parent.name


class ScanError(Exception):
    pass


def scan_pdfs(root_path: str) -> list[PdfEntry]:
    """Procura recursivamente todos os PDFs abaixo de root_path.

    Lança ScanError se a pasta não existir ou não puder ser acessada
    (ex: rede indisponível), para que a interface mostre um aviso claro
    em vez de travar.
    """
    root = Path(root_path)
    if not root.exists():
        raise ScanError(f"Pasta não encontrada ou inacessível: {root_path}")

    entries: list[PdfEntry] = []
    current_keys: set[tuple[str, float]] = set()
    now = time.time()
    try:
        for pdf_path in root.rglob("*.pdf"):
            try:
                stat = pdf_path.stat()
            except OSError:
                continue

            lote_from_text = _cached_lote_from_text(pdf_path, stat.st_mtime)
            if lote_from_text and (now - stat.st_mtime) >= MIN_AGE_SECONDS:
                renamed_path = _rename_to_lote(pdf_path, lote_from_text)
                if renamed_path != pdf_path:
                    pdf_path = renamed_path
                    try:
                        stat = pdf_path.stat()
                    except OSError:
                        continue
                    _text_lote_cache[(str(pdf_path), stat.st_mtime)] = lote_from_text

            key = (str(pdf_path), stat.st_mtime)
            current_keys.add(key)
            lote = lote_from_text or extract_lote(pdf_path)
            entries.append(
                PdfEntry(
                    lote=lote,
                    filename=pdf_path.name,
                    folder=str(pdf_path.parent),
                    full_path=str(pdf_path),
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                )
            )
    except OSError as exc:
        raise ScanError(f"Erro ao ler pasta de rede: {exc}") from exc

    _prune_text_cache(current_keys)
    entries.sort(key=lambda e: e.mtime, reverse=True)
    return entries
