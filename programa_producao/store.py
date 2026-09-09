"""Estado compartilhado entre usuários (Responsável, Qtde Chapas Real, Obs,
status de conclusão).

Os dados ficam em arquivos JSON dentro de <pasta de rede>\\_controle\\, ao
lado dos PDFs. Como todos os usuários apontam para a mesma pasta de rede,
todos enxergam as mesmas informações. Escrita é atômica (arquivo temporário
+ os.replace) para evitar JSON pela metade se duas máquinas salvarem quase
ao mesmo tempo; em caso de conflito real, vale a última gravação.
"""
import getpass
import json
import os
from datetime import datetime
from pathlib import Path

CONTROL_DIR = "_controle"

STATUS_PENDENTE = "pendente"
STATUS_CONCLUIDO = "concluido"


def _record_path(root_path: str, pdf_stem: str) -> Path:
    return Path(root_path) / CONTROL_DIR / f"{pdf_stem}.json"


def empty_record() -> dict:
    return {
        "responsavel": "",
        "status": STATUS_PENDENTE,
        "prioridade": False,
        "concluido_em": "",
        "concluido_por": "",
        "itens": {},
        "comentarios": [],
    }


def load_record(root_path: str, pdf_stem: str) -> dict:
    record = empty_record()
    path = _record_path(root_path, pdf_stem)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                record.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
    else:
        # Se for um novo PDF detectado na pasta, cria o arquivo JSON inicial com status Pendente
        try:
            save_record(root_path, pdf_stem, record)
        except OSError:
            pass
    return record


def save_record(root_path: str, pdf_stem: str, record: dict) -> None:
    path = _record_path(root_path, pdf_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def add_comment(root_path: str, pdf_stem: str, texto: str, autor: str = "") -> dict:
    record = load_record(root_path, pdf_stem)
    if "comentarios" not in record or not isinstance(record["comentarios"], list):
        record["comentarios"] = []

    user_autor = autor.strip() if autor and autor.strip() else ""
    if not user_autor:
        try:
            user_autor = getpass.getuser()
        except Exception:
            user_autor = "Operador"

    comment_entry = {
        "id": f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "autor": user_autor,
        "texto": texto.strip(),
        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    record["comentarios"].append(comment_entry)
    save_record(root_path, pdf_stem, record)
    return comment_entry


def mark_concluido(record: dict) -> dict:
    record["status"] = STATUS_CONCLUIDO
    record["concluido_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        record["concluido_por"] = getpass.getuser()
    except Exception:
        record["concluido_por"] = ""
    return record


def _order_path(root_path: str) -> Path:
    return Path(root_path) / CONTROL_DIR / "ordem_pendentes.json"


def load_pending_order(root_path: str) -> list[str]:
    """Carrega a lista de arquivos pendentes na ordem definida pelo usuário/PCP."""
    if not root_path:
        return []
    path = _order_path(root_path)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict) and "ordem" in saved and isinstance(saved["ordem"], list):
                return [str(x) for x in saved["ordem"]]
            elif isinstance(saved, list):
                return [str(x) for x in saved]
        except (OSError, json.JSONDecodeError):
            pass
    return []


def save_pending_order(root_path: str, order_list: list[str]) -> None:
    """Salva a ordem dos arquivos pendentes de forma atômica."""
    if not root_path:
        return
    path = _order_path(root_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    user_autor = ""
    try:
        user_autor = getpass.getuser()
    except Exception:
        user_autor = "Operador"

    payload = {
        "ordem": order_list,
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "atualizado_por": user_autor,
    }
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

