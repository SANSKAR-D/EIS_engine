# backend/tests/test_rbac_and_hybrid.py
import pytest
from app.clients.decision_client import DecisionPlaneClient
from app.retrieval.hybrid_search import compute_rrf_score, run_expanded_hybrid_search
from app.retrieval.rbac import build_rbac_filter, check_rbac_permission
from app.retrieval.reranker import rerank_candidates


def test_rrf_formula_computation():
    """Verifies reciprocal rank fusion formula: 1/(k + rank_lex) + 1/(k + rank_vec)."""
    # Item ranked 1st lexically and 2nd in vector
    score = compute_rrf_score(rank_lex=1, rank_vec=2, k=60)
    expected = (1.0 / 61.0) + (1.0 / 62.0)
    assert pytest.approx(score, rel=1e-5) == expected


@pytest.mark.asyncio
async def test_t19_rbac_student_vs_hod_isolation():
    """
    T-19: Hybrid search on confidential exam misconduct topic run as STUDENT vs. HOD.
    Asserts: STUDENT receives 0 confidential rows; HOD retrieves full verified hits.
    """
    in_memory_store = {
        "chunks": [
            {
                "chunk_id": "CH_CONF_01",
                "matter_id": "MAT_MISCONDUCT",
                "chunk_type": "EMAIL_BODY",
                "sensitivity_level": "CONFIDENTIAL",
                "allowed_participants": ["dean.admin@northbridge.edu", "prof.exam@northbridge.edu"],
                "content": "Confidential disciplinary inquiry regarding paper leak and exam misconduct in 4th semester.",
            },
            {
                "chunk_id": "CH_PUB_01",
                "matter_id": "MAT_PUB_01",
                "chunk_type": "EMAIL_BODY",
                "sensitivity_level": "PUBLIC",
                "allowed_participants": [],
                "content": "Notice: Final exam timetable released on college portal.",
            },
        ],
        "matters": {},
        "emails": {},
        "case_files": {},
    }

    client = DecisionPlaneClient(use_mock=True)

    # 1. Query as STUDENT: strictly isolated from confidential records
    student_hits = await run_expanded_hybrid_search(
        pool=None,
        query="exam misconduct inquiry",
        role="STUDENT",
        user_email="student01@northbridge.edu",
        in_memory_store=in_memory_store,
        decision_client=client,
    )
    conf_student_hits = [h for h in student_hits if h.get("sensitivity_level") == "CONFIDENTIAL"]
    assert len(conf_student_hits) == 0

    # 2. Query as HOD: receives confidential record with full institutional visibility
    hod_hits = await run_expanded_hybrid_search(
        pool=None,
        query="exam misconduct inquiry",
        role="HOD",
        user_email="mech.hod@northbridge.edu",
        in_memory_store=in_memory_store,
        decision_client=client,
    )
    assert len(hod_hits) >= 1
    assert any(h["chunk_id"] == "CH_CONF_01" for h in hod_hits)


@pytest.mark.asyncio
async def test_t20_faculty_participant_acl_filtering():
    """
    T-20: FACULTY searches a confidential thread they participated in vs. one they did not.
    Asserts: Participant thread returned; non-participant confidential thread strictly excluded.
    """
    in_memory_store = {
        "chunks": [
            # Confidential Thread 1: Faculty IS a participant
            {
                "chunk_id": "CH_FAC_PART",
                "matter_id": "MAT_DISCIPLINARY",
                "chunk_type": "EMAIL_BODY",
                "sensitivity_level": "CONFIDENTIAL",
                "allowed_participants": ["faculty.mech@northbridge.edu", "dean.admin@northbridge.edu"],
                "content": "Confidential student disciplinary hearing notes regarding workshop safety breach.",
            },
            # Confidential Thread 2: Faculty is NOT a participant (Executive Salary review)
            {
                "chunk_id": "CH_EXEC_ONLY",
                "matter_id": "MAT_EXEC_PAY",
                "chunk_type": "EMAIL_BODY",
                "sensitivity_level": "CONFIDENTIAL",
                "allowed_participants": ["dean.admin@northbridge.edu", "finance@northbridge.edu"],
                "content": "Confidential faculty appraisal and executive salary committee revision notes.",
            },
        ],
        "matters": {},
        "emails": {},
        "case_files": {},
    }

    client = DecisionPlaneClient(use_mock=True)

    faculty_hits = await run_expanded_hybrid_search(
        pool=None,
        query="confidential notes",
        role="FACULTY",
        user_email="faculty.mech@northbridge.edu",
        in_memory_store=in_memory_store,
        decision_client=client,
    )

    hit_ids = {h["chunk_id"] for h in faculty_hits}

    # Participant confidential thread returned
    assert "CH_FAC_PART" in hit_ids

    # Non-participant confidential thread strictly excluded
    assert "CH_EXEC_ONLY" not in hit_ids


@pytest.mark.asyncio
async def test_t21_graph_expansion_zero_keyword_approval():
    """
    T-21: Query 'CNC machine procurement' where HoD email E111 says only 'Approved, Option B.'
    Asserts: Graph Expansion injects E111 + compiled Case File into candidate pool before Gate C.
    """
    in_memory_store = {
        "chunks": [
            # Main procurement discussion chunk with lexical match
            {
                "chunk_id": "CH_CNC_01",
                "matter_id": "MAT_CNC",
                "chunk_type": "EMAIL_BODY",
                "sensitivity_level": "INTERNAL",
                "allowed_participants": ["purchase@northbridge.edu", "mech.hod@northbridge.edu"],
                "content": "Quotation evaluation for CNC machine procurement and 3-axis turning centre.",
            }
        ],
        "matters": {
            "MAT_CNC": {
                "matter_id": "MAT_CNC",
                "canonical_title": "CNC Machine Procurement",
                "sensitivity_level": "INTERNAL",
                "emails": [
                    {
                        "email_id": "E111",
                        "matter_id": "MAT_CNC",
                        "sender_email": "mech.hod@northbridge.edu",
                        "clean_body": "Approved, Option B.",
                        "sensitivity_level": "INTERNAL",
                        "participants": ["mech.hod@northbridge.edu", "purchase@northbridge.edu"],
                        "is_binding_approval": True,
                    }
                ],
            }
        },
        "emails": {
            "E111": {
                "email_id": "E111",
                "matter_id": "MAT_CNC",
                "sender_email": "mech.hod@northbridge.edu",
                "clean_body": "Approved, Option B.",
                "sensitivity_level": "INTERNAL",
                "participants": ["mech.hod@northbridge.edu", "purchase@northbridge.edu"],
                "is_binding_approval": True,
            }
        },
        "case_files": {
            "MAT_CNC": {
                "matter_id": "MAT_CNC",
                "summary": "3-axis CNC Turning Centre procurement from Vendor B.",
                "final_decision": "Vendor B approved at INR 17.9 Lakh",
                "approval_email_id": "E111",
            }
        },
    }

    client = DecisionPlaneClient(use_mock=True)

    results = await run_expanded_hybrid_search(
        pool=None,
        query="CNC machine procurement",
        role="HOD",
        user_email="mech.hod@northbridge.edu",
        in_memory_store=in_memory_store,
        decision_client=client,
    )

    # Graph Expansion recovered E111 despite zero lexical overlap with query
    injected_ids = {r.get("candidate_id") or r.get("chunk_id") or r.get("email_id") for r in results}
    assert "E111" in injected_ids
    assert "cf_MAT_CNC" in injected_ids


def test_t22_gate_c_reranker_top5_and_pruning():
    """
    T-22: 20 mixed candidates (3 directly relevant, 17 tangential) scored by Gate C reranker.
    Asserts: All 3 direct hits ranked in top-5 with score >= 2; low-score hits pruned.
    """
    direct_candidates = [
        {
            "candidate_id": "D1",
            "content": "HoD approved Vendor B for CNC Turning Centre at INR 17.9 Lakh.",
        },
        {
            "candidate_id": "D2",
            "content": "Purchase Order draft submitted for CNC Turning Centre Option B.",
        },
        {
            "candidate_id": "D3",
            "content": "Technical specifications comparison for 3-axis CNC lathe machine.",
        },
    ]

    tangential_candidates = [
        {"candidate_id": f"T{i}", "content": f"Tangential notice {i}: Library books fine and cafeteria schedule."}
        for i in range(1, 18)
    ]

    all_20 = direct_candidates + tangential_candidates
    assert len(all_20) == 20

    client = DecisionPlaneClient(use_mock=True)

    reranked = rerank_candidates(
        query="What happened with the CNC machine procurement?",
        candidates=all_20,
        decision_client=client,
        min_score=2,
    )

    # 1. Pruned low-scoring noise (< 2)
    assert len(reranked) <= 5

    # 2. All 3 direct hits are retained in top rankings with score >= 2
    top_ids = {r["candidate_id"] for r in reranked}
    assert "D1" in top_ids
    assert "D2" in top_ids
    assert "D3" in top_ids

    # 3. Direct hits have score >= 2
    for r in reranked:
        assert r["gate_c_score"] >= 2
