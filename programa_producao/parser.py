"""Extrai os dados estruturados do PDF de Separação de Chapas (PP5928).

O PDF é gerado pelo PromobERP com layout fixo:
  Lote: <numero>    <descricao>
  Código | Descrição do Item | Metros | Quantidade | Qtde Chapas Real | Obs
  ...linhas de itens...
  rodapé: "... Emitido por: FULANO em dd/mm/aaaa - hh:mm:ss"

A extração usa as coordenadas das palavras (não a ordem do texto), porque a
ordem interna de desenho do PDF é embaralhada.
"""
import re
from dataclasses import dataclass, field

Y_TOLERANCE = 3.0
NUMERIC = re.compile(r"^[\d.,]+$")
CODIGO = re.compile(r"^[\d]+(\.[\d]+)+$")
EMITIDO = re.compile(r"Emitido por:\s*(.+?)\s+em\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2}:\d{2})")


@dataclass
class ItemRow:
    codigo: str
    descricao: str
    metros: str
    quantidade: str


@dataclass
class PageData:
    lote: str = ""
    descricao: str = ""
    emitido_por: str = ""
    emitido_em: str = ""
    rows: list = field(default_factory=list)


class ParseError(Exception):
    pass


def _group_lines(words):
    """Agrupa palavras por linha (mesma coordenada y, com tolerância)."""
    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        x0, y0, _x1, _y1, text = w[0], w[1], w[2], w[3], w[4]
        for line in lines:
            if abs(line["y"] - y0) <= Y_TOLERANCE:
                line["words"].append((x0, text))
                break
        else:
            lines.append({"y": y0, "words": [(x0, text)]})
    for line in lines:
        line["words"].sort()
    return sorted(lines, key=lambda l: l["y"])


def _parse_page(page) -> PageData:
    data = PageData()
    words = page.get_text("words")
    full_text = page.get_text()

    m = EMITIDO.search(full_text)
    if m:
        data.emitido_por = m.group(1).strip()
        data.emitido_em = f"{m.group(2)} {m.group(3)}"

    lines = _group_lines(words)

    header_y = None
    footer_y = None
    for line in lines:
        texts = [t for _x, t in line["words"]]
        joined = " ".join(texts)
        if "Lote:" in texts:
            idx = texts.index("Lote:")
            rest = line["words"][idx + 1:]
            if rest:
                # O valor do lote pode vir quebrado em várias palavras
                # ("3399," "3407"). A descrição vem bem mais à direita e pode
                # começar com número ("24 LARANJA-DS65"), então só continuamos
                # juntando tokens numéricos enquanto estiverem próximos.
                j = 1
                while (
                    j < len(rest)
                    and NUMERIC.match(rest[j][1].rstrip(","))
                    and rest[j][0] - rest[j - 1][0] < 60
                ):
                    j += 1
                lote_raw = " ".join(t for _x, t in rest[:j])
                data.lote = re.sub(r"\s*,\s*", ",", lote_raw).strip(",")
                data.descricao = " ".join(t for _x, t in rest[j:]).strip()
        elif "Metros" in texts and "Quantidade" in joined:
            header_y = line["y"]
        elif "Emitido" in texts or "PROMOB" in texts:
            footer_y = line["y"]

    if header_y is None:
        return data

    for line in lines:
        if line["y"] <= header_y + Y_TOLERANCE:
            continue
        if footer_y is not None and line["y"] >= footer_y - 5:
            continue
        tokens = [t for _x, t in line["words"]]
        if not tokens or not CODIGO.match(tokens[0]):
            continue
        codigo = tokens[0]
        rest = tokens[1:]
        trailing_numeric = []
        while rest and NUMERIC.match(rest[-1]):
            trailing_numeric.insert(0, rest.pop())
        if len(trailing_numeric) >= 2:
            metros, quantidade = trailing_numeric[-2], trailing_numeric[-1]
            rest += trailing_numeric[:-2]
        elif len(trailing_numeric) == 1:
            metros, quantidade = "", trailing_numeric[0]
        else:
            metros, quantidade = "", ""
        data.rows.append(
            ItemRow(codigo=codigo, descricao=" ".join(rest), metros=metros, quantidade=quantidade)
        )
    return data


def parse_pdf(pdf_path: str) -> list:
    """Devolve uma lista de PageData (uma por página que tenha itens)."""
    try:
        import pymupdf
    except ImportError as exc:
        raise ParseError("A biblioteca PyMuPDF não está instalada.") from exc

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise ParseError(f"Não foi possível abrir o PDF:\n{exc}") from exc

    pages = []
    try:
        for page in doc:
            data = _parse_page(page)
            if data.rows or data.lote:
                pages.append(data)
    finally:
        doc.close()

    if not pages:
        raise ParseError("Nenhum dado de separação de chapas encontrado neste PDF.")
    return pages
