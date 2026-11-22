# backend/tests/test_mcp_boundary.py
import pytest
from fastmcp import Client as FastMCPClient

from app.mcp_server.server import mcp, set_mcp_in_memory_store
from app.security_context import _principal_ctx, set_principal


@pytest.mark.asyncio
async def test_t23_mcp_tool_schemas_hide_rbac_parameters():
    """
    T-23: Inspect JSON schemas exported by all 6 FastMCP tools via mcp_client.list_tools().
    Asserts: None of the 6 tool schemas expose role, active_role, or user_email parameters.
    """
    async with FastMCPClient(mcp) as client:
        tools = await client.list_tools()
        # Exactly 6 standardized tools exposed
        assert len(tools) == 6

        expected_tools = {
            "search_hybrid_with_expansion",
            "get_matter_timeline",
            "inspect_attachment_page",
            "get_raw_email",
            "get_stalled_approvals",
            "get_quarantine_summary",
        }
        tool_names = {t.name for t in tools}
        assert tool_names == expected_tools

        for tool in tools:
            # Check properties in schema
            schema = tool.input_schema if hasattr(tool, "input_schema") else getattr(tool, "inputSchema", {})
            props = schema.get("properties", {})
            # Verify security parameters are completely absent from LLM-visible schema
            assert "role" not in props, f"Security leak: 'role' exposed in {tool.name}"
            assert "active_role" not in props, f"Security leak: 'active_role' exposed in {tool.name}"
            assert "user_email" not in props, f"Security leak: 'user_email' exposed in {tool.name}"


@pytest.mark.asyncio
async def test_t24_mcp_quarantine_blocks_student_role():
    """
    T-24: Invoke get_quarantine_summary() under STUDENT principal vs. HOD principal.
    Asserts: STUDENT receives {"error": "FORBIDDEN"}; HOD receives quarantine list.
    """
    mock_store = {
        "quarantine": [
            {
                "email_id": "E_SPAM_01",
                "spam_probability": 0.96,
                "status": "AUTO_QUARANTINED",
                "sender_email": "sales@promo.com",
            }
        ]
    }
    set_mcp_in_memory_store(mock_store)

    try:
        # 1. Test as STUDENT -> FORBIDDEN
        token = set_principal("STUDENT", "student01@northbridge.edu")
        try:
            async with FastMCPClient(mcp) as client:
                res = await client.call_tool("get_quarantine_summary", {"limit": 10})
                assert isinstance(res.data, dict)
                assert res.data.get("error") == "FORBIDDEN"
        finally:
            _principal_ctx.reset(token)

        # 2. Test as HOD -> Allowed
        token_hod = set_principal("HOD", "mech.hod@northbridge.edu")
        try:
            async with FastMCPClient(mcp) as client:
                res_hod = await client.call_tool("get_quarantine_summary", {"limit": 10})
                assert isinstance(res_hod.data, dict)
                assert res_hod.data.get("error") != "FORBIDDEN"
                assert "quarantined_emails" in res_hod.data
                assert len(res_hod.data["quarantined_emails"]) == 1
        finally:
            _principal_ctx.reset(token_hod)
    finally:
        set_mcp_in_memory_store(None)


@pytest.mark.asyncio
async def test_t25_mcp_inspect_attachment_enforces_parent_rbac():
    """
    T-25: Invoke inspect_attachment_page('E_CONF', 'Letter.pdf', 1) under STUDENT.
    Asserts: Tool enforces parent email RBAC and denies access without returning page text.
    """
    mock_store = {
        "emails": {
            "E_CONF": {
                "email_id": "E_CONF",
                "sensitivity_level": "CONFIDENTIAL",
                "participants": ["mech.hod@northbridge.edu", "dean.admin@northbridge.edu"],
            }
        },
        "pages": {
            "E_CONF:Letter.pdf:1": {
                "email_id": "E_CONF",
                "filename": "Letter.pdf",
                "page_number": 1,
                "sensitivity_level": "CONFIDENTIAL",
                "participants": ["mech.hod@northbridge.edu", "dean.admin@northbridge.edu"],
                "extracted_text": "Confidential disciplinary committee proceedings.",
            }
        },
    }
    set_mcp_in_memory_store(mock_store)

    try:
        # 1. Under STUDENT principal: access strictly denied
        token_student = set_principal("STUDENT", "student01@northbridge.edu")
        try:
            async with FastMCPClient(mcp) as client:
                res_student = await client.call_tool(
                    "inspect_attachment_page",
                    {"email_id": "E_CONF", "filename": "Letter.pdf", "page_number": 1},
                )
                assert isinstance(res_student.data, dict)
                assert res_student.data.get("error") == "FORBIDDEN"
                assert "extracted_text" not in res_student.data
        finally:
            _principal_ctx.reset(token_student)

        # 2. Under HOD principal: access permitted
        token_hod = set_principal("HOD", "mech.hod@northbridge.edu")
        try:
            async with FastMCPClient(mcp) as client:
                res_hod = await client.call_tool(
                    "inspect_attachment_page",
                    {"email_id": "E_CONF", "filename": "Letter.pdf", "page_number": 1},
                )
                assert isinstance(res_hod.data, dict)
                assert res_hod.data.get("error") != "FORBIDDEN"
                assert "extracted_text" in res_hod.data
                assert "disciplinary committee" in res_hod.data["extracted_text"]
        finally:
            _principal_ctx.reset(token_hod)

    finally:
        set_mcp_in_memory_store(None)
