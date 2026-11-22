# backend/app/retrieval/__init__.py
from app.retrieval.rbac import (
    build_rbac_filter,
    check_rbac_permission,
    fetch_authorized_attachment_page,
    fetch_authorized_email,
    fetch_authorized_matter_timeline,
)
from app.retrieval.hybrid_search import compute_rrf_score, run_expanded_hybrid_search
from app.retrieval.reranker import rerank_candidates
