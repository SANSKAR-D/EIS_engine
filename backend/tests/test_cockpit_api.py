# backend/tests/test_cockpit_api.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data.get("cockpit_ready") is True
        assert data.get("phase") == "Phase 9 - React Institutional Cockpit"


@pytest.mark.asyncio
async def test_query_hod_authorized_canonical():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/query",
            json={"query": "What happened with the CNC machine procurement?"},
            headers={"X-Active-Role": "HOD", "X-User-Email": "hod.mech@institution.edu"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["abstained"] is False
        assert "Vendor B" in data["final_decision"]
        assert len(data["claims"]) == 2
        assert len(data["agent_trace"]) >= 4
        # Verify citation structure
        c1 = data["claims"][0]
        assert c1["sources"][0]["attachment_filename"] == "Vendor_Comparison.pdf"
        assert c1["entailment_score"] >= 0.95


@pytest.mark.asyncio
async def test_query_student_rbac_abstention():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/query",
            json={"query": "What happened with the CNC machine procurement?"},
            headers={"X-Active-Role": "STUDENT", "X-User-Email": "student@institution.edu"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["abstained"] is True
        assert "Access Restricted" in data["summary"]
        assert len(data["claims"]) == 0


@pytest.mark.asyncio
async def test_matters_and_timeline():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # HOD sees all matters
        res = await client.get("/api/v1/matters", headers={"X-Active-Role": "HOD"})
        assert res.status_code == 200
        matters = res.json()["matters"]
        assert any(m["matter_id"] == "MAT-2026-CNC" for m in matters)

        # Timeline for MAT-2026-CNC
        t_res = await client.get("/api/v1/matters/MAT-2026-CNC/timeline", headers={"X-Active-Role": "HOD"})
        assert t_res.status_code == 200
        t_data = t_res.json()
        assert len(t_data["decisions"]) >= 3
        # Check supersession
        superseded = [d for d in t_data["decisions"] if d["status"] == "SUPERSEDED"]
        assert len(superseded) >= 1
        assert superseded[0]["superseded_by_email"] == "E111"


@pytest.mark.asyncio
async def test_sources_citation_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/sources/E102", headers={"X-Active-Role": "HOD"})
        assert res.status_code == 200
        data = res.json()
        assert data["email_id"] == "E102"
        assert len(data["attachments"]) == 1
        assert "Vendor B" in data["attachments"][0]["markdown_table"]

        # Student access blocked to internal email E102
        s_res = await client.get("/api/v1/sources/E102", headers={"X-Active-Role": "STUDENT"})
        assert s_res.status_code == 403


@pytest.mark.asyncio
async def test_quarantine_rbac_and_restore():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Student blocked
        s_res = await client.get("/api/v1/quarantine", headers={"X-Active-Role": "STUDENT"})
        assert s_res.status_code == 403

        # HOD allowed
        h_res = await client.get("/api/v1/quarantine", headers={"X-Active-Role": "HOD"})
        assert h_res.status_code == 200
        q_data = h_res.json()
        assert len(q_data["items"]) >= 2
        assert q_data["metrics"]["estimated_ocr_pages_saved"] > 0

        # Restore
        r_res = await client.post("/api/v1/quarantine/Q-901/restore", headers={"X-Active-Role": "HOD"})
        assert r_res.status_code == 200
        assert r_res.json()["status"] == "RESTORED"


@pytest.mark.asyncio
async def test_radar_stalls_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/radar/stalls", headers={"X-Active-Role": "HOD"})
        assert res.status_code == 200
        data = res.json()
        assert len(data["stalled_items"]) >= 1
        assert len(data["upcoming_deadlines"]) >= 2
