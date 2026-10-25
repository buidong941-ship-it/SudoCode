"""RAG cho kho chính sách `policy/`: chunk theo mã mục `[XX-nn]`, tìm lai (vector + BM25), có luật phiên bản và tài liệu nội bộ.

Mỗi mục `## [XX-nn]` là một chunk — đúng `chunk_id` BTC dùng để gán nhãn Recall@k (rag/qa_labeled.json), nên không cần ánh xạ.

Ba luật áp trước khi xếp hạng (không giao cho LLM tự quyết):
- **Phiên bản:** tài liệu HẾT HIỆU LỰC (`DT-OLD-*`) chỉ được dùng khi câu hỏi gắn với đơn tạo trước ngày bản mới có hiệu lực
  (`order_date < 2026-10-01`, theo `changelog.md` CL-01). Mặc định bị loại, nên "14 ngày" của bản cũ không lọt vào câu trả lời.
- **Nội bộ:** chunk của tài liệu `NOI-BO` vẫn được truy hồi (để biết câu hỏi đang chạm vào thông tin cấm) nhưng mang cờ
  `restricted`; `search()` cho agent không bao giờ trả nội dung của chúng.
- **Nhiễu:** nội quy nhân viên không phải thông tin cho khách → loại.

Cấu hình bằng biến môi trường (mặc định nhắm tới server có GPU; máy yếu tự lùi xuống, không cần sửa code):
- `EMBED_MODEL`  model embedding. Mặc định `BAAI/bge-m3`; ở chế độ `auto`, nếu máy chưa có model này thì dùng
                 `intfloat/multilingual-e5-small` (nếu có), rồi mới lùi về BM25.
- `EMBED_DEVICE` `cuda` | `cpu`; mặc định tự chọn GPU nếu có.
- `RERANK_MODEL` cross-encoder xếp hạng lại top-`RERANK_TOP_N` (20) ứng viên. Mặc định `off`; trên server đặt
                 `BAAI/bge-reranker-v2-m3`. Phải đo có/không có reranker rồi mới giữ: reranker không hợp tiếng Việt làm
                 Recall giảm (thử với một cross-encoder tiếng Anh nhỏ: Recall@3 91,5% → 81,4%).
- `RAG_STORE`    `numpy` (mặc định: ma trận lưu ở `data/rag/`) | `pgvector` (bảng `policy_chunks` trong Postgres ở `DATABASE_URL`,
                 xem docker-compose.yml). Với 99 chunk hai cách cho cùng kết quả; pgvector để dành cho kho lớn / nhiều tiến trình.
- `RAG_MODE`     `auto` (mặc định: lai nếu có model trên máy, không thì BM25) | `hybrid` | `bm25`.
Tải model một lần: `python run_rag_eval.py --download`.
"""
import glob
import hashlib
import math
import os
import re
from collections import Counter

from core import log as cclog
from core.config import ROOT, settings
from harness.textnorm import fold

log = cclog.get("rag")
CHUNK_RX = re.compile(r"^## \[([A-Z0-9]+(?:-[A-Z0-9]+)*)\]\s*(.*?)\n(.*?)(?=^## \[|\Z)", re.S | re.M)
OLD_POLICY_EFFECTIVE_UNTIL = "2026-10-01"
STOP = set("a anh chi em minh co khong la cua cho va thi o nhe da duoc bao nhieu the nao gi nao ben vay roi nhu neu "
           "thi cac nhung mot nay do khi se bi".split())
EMBED_MODEL = os.environ.get("EMBED_MODEL") or "BAAI/bge-m3"
EMBED_FALLBACKS = ["intfloat/multilingual-e5-small"]
RERANK_MODEL = os.environ.get("RERANK_MODEL") or "off"
RERANK_TOP_N = int(os.environ.get("RERANK_TOP_N") or 20)
RAG_STORE = (os.environ.get("RAG_STORE") or "numpy").lower()
RAG_MODE = (os.environ.get("RAG_MODE") or "auto").lower()
INDEX_DIR = os.path.join(ROOT, "data", "rag")


def _device():
    d = (os.environ.get("EMBED_DEVICE") or "auto").lower()
    if d != "auto":
        return d
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _load(cls, name, **kw):
    try:
        return cls(name, device=_device(), local_files_only=True, **kw)
    except Exception:
        if os.environ.get("RAG_ALLOW_DOWNLOAD") != "1":
            raise
        return cls(name, device=_device(), **kw)


def load_chunks(policy_dir=None):
    out = []
    for f in sorted(glob.glob(os.path.join(policy_dir or os.path.join(settings.btc_dir, "policy"), "*.md"))):
        doc = os.path.basename(f)
        txt = open(f, encoding="utf-8").read()
        h1 = re.search(r"^# (.+)$", txt, re.M)
        doc_title = re.sub(r"[*`\[\]]|—\s*Shop BTC.*$", "", h1.group(1)).strip() if h1 else doc
        for m in CHUNK_RX.finditer(txt):
            out.append({"chunk_id": m.group(1), "doc": doc, "doc_title": doc_title, "title": m.group(2).strip(), "text": m.group(3).strip(),
                        "restricted": "NOI-BO" in doc, "superseded": "HET-HIEU-LUC" in doc, "noise": "noi-quy-nhan-vien" in doc})
    return out


CHUNKS = load_chunks()


def _toks(s):
    return [w for w in re.findall(r"[a-z0-9]+", fold(s)) if w not in STOP and len(w) > 1]


def _doc_text(c):
    return c["doc_title"] + " — " + c["title"] + ". " + c["text"]


def expand_query(query):
    try:
        from harness.tools import find_products
        skus = find_products(query)
    except Exception:
        skus = []
    return query + (" " + " ".join(skus) if skus else "")


class _BM25:
    def __init__(self, chunks, k1=1.4, b=0.6):
        self.docs = [Counter(_toks(c["doc_title"] + " " + c["title"] + " " + c["title"] + " " + c["text"])) for c in chunks]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / max(1, len(self.len))
        self.df = Counter(w for d in self.docs for w in d)
        self.n, self.k1, self.b = len(chunks), k1, b

    def scores(self, query):
        q = set(_toks(query))
        out = []
        for d, ln in zip(self.docs, self.len):
            s = 0.0
            for w in q:
                tf = d.get(w, 0)
                if tf:
                    idf = math.log(1 + (self.n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * ln / self.avg))
            out.append(s)
        return out


class _Index:
    def __init__(self, chunks, model_name):
        import numpy as np
        from sentence_transformers import SentenceTransformer
        self.np, self.name, self.chunks = np, model_name, chunks
        self.e5 = "e5" in model_name.lower()
        self.model = _load(SentenceTransformer, model_name)
        self.sig = hashlib.sha1((model_name + "".join(c["chunk_id"] + _doc_text(c) for c in chunks)).encode()).hexdigest()[:16]
        self.pg = None
        if RAG_STORE == "pgvector":
            self._init_pgvector()
        else:
            path = os.path.join(INDEX_DIR, f"{re.sub(r'[^A-Za-z0-9]+', '-', model_name)}-{self.sig}.npy")
            if os.path.exists(path):
                self.mat = np.load(path)
            else:
                self.mat = self._encode([_doc_text(c) for c in chunks], query=False)
                os.makedirs(INDEX_DIR, exist_ok=True)
                np.save(path, self.mat)

    def _encode(self, texts, query):
        if self.e5:
            texts = [("query: " if query else "passage: ") + t for t in texts]
        return self.model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)

    def _init_pgvector(self):
        import psycopg
        url = settings.database_url
        if not url.startswith("postgresql"):
            raise RuntimeError("RAG_STORE=pgvector cần DATABASE_URL=postgresql+psycopg://… (docker compose up -d db)")
        self.pg = psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
        dim = self.model.get_sentence_embedding_dimension()
        with self.pg.cursor() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute("CREATE TABLE IF NOT EXISTS policy_chunks (index_sig text, pos int, chunk_id text, doc text, "
                      "restricted boolean, superseded boolean, embedding vector, PRIMARY KEY (index_sig, pos))")
            c.execute("SELECT count(*) FROM policy_chunks WHERE index_sig = %s", (self.sig,))
            if c.fetchone()[0] != len(self.chunks):
                c.execute("DELETE FROM policy_chunks WHERE index_sig = %s", (self.sig,))
                mat = self._encode([_doc_text(ch) for ch in self.chunks], query=False)
                for i, (ch, v) in enumerate(zip(self.chunks, mat)):
                    c.execute("INSERT INTO policy_chunks VALUES (%s, %s, %s, %s, %s, %s, %s::vector)",
                              (self.sig, i, ch["chunk_id"], ch["doc"], ch["restricted"], ch["superseded"], _vec_literal(v)))
                log.info("pgvector: đã nạp %d chunk (dim %d, index %s)", len(self.chunks), dim, self.sig)

    def scores(self, query):
        q = self._encode([query], query=True)[0]
        if self.pg is None:
            return (self.mat @ q).tolist()
        out = [0.0] * len(self.chunks)
        with self.pg.cursor() as c:
            c.execute("SELECT pos, 1 - (embedding <=> %s::vector) FROM policy_chunks WHERE index_sig = %s", (_vec_literal(q), self.sig))
            for pos, sim in c.fetchall():
                out[pos] = float(sim)
        return out


def _vec_literal(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class _Reranker:
    def __init__(self, model_name):
        from sentence_transformers import CrossEncoder
        self.name = model_name
        self.model = _load(CrossEncoder, model_name, max_length=512)

    def scores(self, query, texts):
        return [float(x) for x in self.model.predict([(query, t) for t in texts], batch_size=16, show_progress_bar=False)]


_bm25 = _BM25(CHUNKS)
_index, _index_err = None, None
_reranker, _reranker_err = None, None


def _vector():
    global _index, _index_err
    if RAG_MODE == "bm25" or _index_err:
        return None
    if _index is None:
        names = [EMBED_MODEL] + ([m for m in EMBED_FALLBACKS if m != EMBED_MODEL] if RAG_MODE == "auto" else [])
        errs = []
        for name in names:
            try:
                _index = _Index(CHUNKS, name)
                log.info("RAG vector sẵn sàng: %s trên %s, kho %s, %d chunk", name, _device(), RAG_STORE, len(CHUNKS))
                break
            except Exception as e:
                errs.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
        if _index is None:
            _index_err = "; ".join(errs)
            if RAG_MODE == "hybrid":
                raise RuntimeError(f"RAG_MODE=hybrid nhưng không nạp được model embedding ({_index_err}) "
                                   f"— tải một lần bằng `python run_rag_eval.py --download`")
            log.warning("không nạp được model embedding (%s) → dùng BM25", _index_err[:200])
            return None
    return _index


def _rerank():
    global _reranker, _reranker_err
    if RERANK_MODEL.lower() in ("off", "none", "0") or _reranker_err or _vector() is None:
        return None
    if _reranker is None:
        try:
            _reranker = _Reranker(RERANK_MODEL)
            log.info("RAG reranker sẵn sàng: %s", RERANK_MODEL)
        except Exception as e:
            _reranker_err = f"{type(e).__name__}: {str(e)[:120]}"
            log.info("không có reranker %s trên máy (%s) → bỏ bước xếp hạng lại", RERANK_MODEL, _reranker_err)
            return None
    return _reranker


def mode():
    return "hybrid" if _vector() is not None else "bm25"


def describe():
    v, r = _vector(), _rerank()
    return {"mode": "hybrid" if v else "bm25", "embed_model": v.name if v else None, "device": _device() if v else None,
            "store": ("pgvector" if v and v.pg is not None else "numpy") if v else None, "reranker": r.name if r else None,
            "n_chunks": len(CHUNKS)}


def _allowed(c, order_date):
    if c["noise"]:
        return False
    if c["superseded"]:
        return bool(order_date and order_date < OLD_POLICY_EFFECTIVE_UNTIL)
    return True


def retrieve(query, k=5, order_date=None, rrf_k=60):
    lex = _bm25.scores(expand_query(query))
    vec = _vector()
    dense = vec.scores(query) if vec else None
    ids = [i for i, c in enumerate(CHUNKS) if _allowed(c, order_date)]
    rank_lex = {i: r for r, i in enumerate(sorted((i for i in ids if lex[i] > 0), key=lambda i: -lex[i]))}
    rank_den = {i: r for r, i in enumerate(sorted(ids, key=lambda i: -dense[i]))} if dense else {}
    fused = []
    for i in ids:
        s = (1 / (rrf_k + rank_lex[i]) if i in rank_lex else 0) + (1 / (rrf_k + rank_den[i]) if i in rank_den else 0)
        if s > 0:
            fused.append((s, i))
    fused.sort(key=lambda x: -x[0])
    rr = _rerank()
    rerank = {}
    if rr and fused:
        cand = fused[:max(RERANK_TOP_N, k)]
        sc = rr.scores(query, [_doc_text(CHUNKS[i]) for _, i in cand])
        rerank = {i: s for (_, i), s in zip(cand, sc)}
        fused = sorted(cand, key=lambda x: -rerank[x[1]])
    return [dict(CHUNKS[i], score=round(s, 5), dense=round(dense[i], 4) if dense else None, bm25=round(lex[i], 3),
                 rerank=round(rerank[i], 4) if i in rerank else None)
            for s, i in fused[:k]]


def search(query, k=3, include_restricted=False, order_date=None):
    hits = retrieve(query, k=k + 4, order_date=order_date)
    return [h for h in hits if include_restricted or not h["restricted"]][:k]


def touches_restricted(query, order_date=None):
    hits = retrieve(query, k=1, order_date=order_date)
    return bool(hits and hits[0]["restricted"])
