"""
app/graph.py
============
Stateful LangGraph Agent Workflow for GoAified HR/IT Helpdesk:
Nodes:
1. Guardrail Node (Prompt injection defense, PII redaction, topic routing)
2. RAG Policy Node (Source-cited retrieval across HR & IT policy documents)
3. PostgreSQL MCP Tool Node (Direct transactional queries for leaves & IT tickets)
4. Response Synthesis Node (Final contextual assembly with citations and PII notices)

Supports LangGraph native StateGraph with a zero-friction fallback runner.
Configurable Gemini model (gemini-2.5-flash / gemini-1.5-flash via langchain-google-genai).
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional, TypedDict, Callable
from pydantic import BaseModel, Field

from app.guardrails import apply_guardrails, GuardrailResult
from app.rag import query_policy, RAGResult
from app.mcp_server import (
    get_employee_leave_balance,
    get_employee_profile,
    get_it_tickets,
    create_it_ticket,
    AVAILABLE_TOOLS
)

logger = logging.getLogger("helpdesk.graph")
logging.basicConfig(level=logging.INFO)

# =====================================================================
# State Definition
# =====================================================================

class AgentState(TypedDict):
    employee_id: str
    raw_query: str
    redacted_query: str
    detected_pii: List[str]
    is_safe: bool
    blocked_reason: Optional[str]
    routed_domain: str
    intent: Optional[str]
    rag_result: Optional[Dict[str, Any]]
    mcp_result: Optional[Dict[str, Any]]
    final_response: str
    step_history: List[str]


# =====================================================================
# Optional Gemini LLM Initialization
# =====================================================================

def get_gemini_llm():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key:
        logger.info("No GOOGLE_API_KEY provided; operating in deterministic policy synthesis mode.")
        return None

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.2)
        logger.info("Initialized Gemini LLM (%s) via langchain-google-genai", model_name)
        return llm
    except Exception as e:
        logger.warning("Could not initialize ChatGoogleGenerativeAI (%s); falling back to rule-based engine.", e)
        return None

gemini_llm = get_gemini_llm()


# =====================================================================
# Workflow Nodes
# =====================================================================

def guardrail_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 1: Execute Prompt-Injection, PII Redaction, and Scope checks.
    """
    logger.info("[Node: guardrail_node] Processing query for %s", state.get("employee_id"))
    res: GuardrailResult = apply_guardrails(state["raw_query"], state.get("employee_id"))
    
    steps = state.get("step_history", []) + ["guardrail_node"]
    return {
        "redacted_query": res.redacted_query,
        "detected_pii": res.detected_pii,
        "is_safe": res.is_safe,
        "blocked_reason": res.blocked_reason,
        "routed_domain": res.routed_domain,
        "intent": res.intent,
        "step_history": steps
    }


def mcp_tool_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 2A: Query PostgreSQL via MCP Server Tools for employee-specific records.
    """
    logger.info("[Node: mcp_tool_node] Calling PostgreSQL MCP tools")
    employee_id = state.get("employee_id", "EMP001")
    query_lower = state["redacted_query"].lower()
    tool_result = {}

    # Check for Ticket Creation Intent
    if any(k in query_lower for k in ["raise an it ticket", "raise a ticket", "create a ticket", "ticket for", "flickering"]):
        # Determine issue type and priority
        issue_type = "Hardware Defect / Screen Flickering" if "flicker" in query_lower or "screen" in query_lower else "IT Support Request"
        priority = "HIGH" if "flicker" in query_lower or "urgent" in query_lower or "critical" in query_lower else "MEDIUM"
        
        # Clean description
        desc = state["redacted_query"]
        tool_result = create_it_ticket(
            employee_id=employee_id,
            issue_type=issue_type,
            description=desc,
            priority=priority
        )

    # Check for Ticket Status Inquiry
    elif any(k in query_lower for k in ["my it tickets", "my tickets", "status of my ticket", "existing it"]):
        tool_result = get_it_tickets(employee_id=employee_id)

    # Check for Profile Inquiry
    elif any(k in query_lower for k in ["my manager", "my department", "who is my manager", "my profile"]):
        tool_result = get_employee_profile(employee_id=employee_id)

    # Default to Leave Balance Inquiry
    else:
        tool_result = get_employee_leave_balance(employee_id=employee_id)

    steps = state.get("step_history", []) + ["mcp_tool_node"]
    return {
        "mcp_result": tool_result,
        "step_history": steps
    }


def rag_policy_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 2B: Query Vector Store / Knowledge Base for HR/IT Policies with explicit citations.
    """
    logger.info("[Node: rag_policy_node] Querying policy knowledge base")
    res: RAGResult = query_policy(state["redacted_query"], llm=gemini_llm)
    steps = state.get("step_history", []) + ["rag_policy_node"]
    return {
        "rag_result": res.model_dump(),
        "step_history": steps
    }


def response_synthesis_node(state: AgentState) -> Dict[str, Any]:
    """
    Step 3: Synthesize final authoritative response incorporating citations, MCP results, or block notices.
    """
    logger.info("[Node: response_synthesis_node] Synthesizing final response")
    steps = state.get("step_history", []) + ["response_synthesis_node"]
    detected_pii = state.get("detected_pii", [])
    
    pii_notice = ""
    if detected_pii:
        pii_notice = (
            f"\n\n> 🛡️ **Privacy Guardrail Notice:** For your security, sensitive data "
            f"({', '.join(detected_pii)}) was redacted before being processed or logged."
        )

    # Case 1: Blocked by Guardrail (Prompt Injection or Off-topic)
    if not state.get("is_safe", True):
        blocked_msg = (
            f"⚠️ **Request Restricted**\n\n"
            f"{state.get('blocked_reason')}\n\n"
            f"*GoAified AI Helpdesk is dedicated exclusively to internal HR policies, "
            f"employee leave/benefits queries, and IT service desk workflows.*"
        )
        return {
            "final_response": blocked_msg + pii_notice,
            "step_history": steps
        }

    # Case 2: MCP Tool Execution Result
    if state.get("mcp_result"):
        mcp = state["mcp_result"]
        # Format leave balance
        if "leave_balances" in mcp:
            lb = mcp["leave_balances"]
            resp = (
                f"### Employee Leave Balance Report\n"
                f"**Employee ID:** {mcp.get('employee_id')} | **Name:** {mcp.get('name')}\n"
                f"**Role:** {mcp.get('role')} ({mcp.get('department')})\n\n"
                f"| Leave Category | Remaining Days |\n"
                f"| :--- | :--- |\n"
                f"| **Casual Leave (CL)** | **{lb['casual_leave']} days** |\n"
                f"| **Sick Leave (SL)** | **{lb['sick_leave']} days** |\n"
                f"| **Earned Leave (EL)** | **{lb['earned_leave']} days** |\n"
                f"| **Total Available Paid Leave** | **{lb['total_available']} days** |\n\n"
                f"*Note: Casual and Sick leaves lapse on Dec 31. Up to 10 Earned leaves can be carried forward.*"
            )
        # Format Ticket Creation
        elif "ticket_id" in mcp and mcp.get("ticket_status") == "OPEN":
            resp = (
                f"### 🎫 IT Support Ticket Created\n"
                f"Your request has been logged successfully in our PostgreSQL IT service desk:\n\n"
                f"- **Ticket ID:** `{mcp.get('ticket_id')}`\n"
                f"- **Issue Category:** {mcp.get('issue_type')}\n"
                f"- **Assigned Priority:** `{mcp.get('priority')}`\n"
                f"- **Status:** `{mcp.get('ticket_status')}`\n"
                f"- **Logged At:** {mcp.get('created_at')}\n\n"
                f"An IT support engineer will review your issue within **4 hours** per our High-Priority SLA."
            )
        # Format Ticket List
        elif "tickets" in mcp:
            tickets = mcp.get("tickets", [])
            if not tickets:
                resp = f"You currently have no active or past IT support tickets on record."
            else:
                rows = "\n".join([
                    f"| `{t['ticket_id']}` | {t['issue_type']} | `{t['status']}` | `{t['priority']}` | {t['created_at']} |"
                    for t in tickets
                ])
                resp = (
                    f"### Your Registered IT Support Tickets\n"
                    f"Found **{len(tickets)}** ticket(s) for Employee `{mcp.get('employee_id')}`:\n\n"
                    f"| Ticket ID | Category | Status | Priority | Created At |\n"
                    f"| :--- | :--- | :--- | :--- | :--- |\n"
                    f"{rows}"
                )
        else:
            resp = json.dumps(mcp, indent=2)

        return {
            "final_response": resp + pii_notice,
            "step_history": steps
        }

    # Case 3: RAG Policy Result
    if state.get("rag_result"):
        rag = state["rag_result"]
        return {
            "final_response": rag.get("answer", "") + pii_notice,
            "step_history": steps
        }

    # Fallback
    return {
        "final_response": "Your request has been processed." + pii_notice,
        "step_history": steps
    }


# =====================================================================
# LangGraph Workflow Construction
# =====================================================================

def route_next_step(state: AgentState) -> str:
    """Routing logic based on guardrail inspection."""
    if not state.get("is_safe", True):
        return "response_synthesis_node"
    
    domain = state.get("routed_domain")
    if domain == "EMPLOYEE_MCP":
        return "mcp_tool_node"
    elif domain in ["HR_POLICY", "IT_POLICY"]:
        return "rag_policy_node"
    else:
        return "response_synthesis_node"


def create_helpdesk_graph():
    """
    Build and compile the LangGraph StateGraph.
    Falls back gracefully to an identical native execution loop if langgraph is not installed.
    """
    try:
        from langgraph.graph import StateGraph, END
        
        workflow = StateGraph(AgentState)
        workflow.add_node("guardrail_node", guardrail_node)
        workflow.add_node("mcp_tool_node", mcp_tool_node)
        workflow.add_node("rag_policy_node", rag_policy_node)
        workflow.add_node("response_synthesis_node", response_synthesis_node)

        workflow.set_entry_point("guardrail_node")

        workflow.add_conditional_edges(
            "guardrail_node",
            route_next_step,
            {
                "mcp_tool_node": "mcp_tool_node",
                "rag_policy_node": "rag_policy_node",
                "response_synthesis_node": "response_synthesis_node"
            }
        )

        workflow.add_edge("mcp_tool_node", "response_synthesis_node")
        workflow.add_edge("rag_policy_node", "response_synthesis_node")
        workflow.add_edge("response_synthesis_node", END)

        compiled_app = workflow.compile()
        logger.info("Successfully compiled LangGraph StateGraph agent workflow.")
        return compiled_app

    except Exception as e:
        logger.info("Using native StateGraph workflow runner: %s", e)
        
        class NativeStateGraphRunner:
            """Faithful standalone executor of the exact StateGraph state machine."""
            def invoke(self, initial_state: AgentState) -> AgentState:
                state = dict(initial_state)
                # 1. Guardrail
                update = guardrail_node(state)
                state.update(update)

                # 2. Conditional edge
                next_node = route_next_step(state)
                if next_node == "mcp_tool_node":
                    update = mcp_tool_node(state)
                    state.update(update)
                elif next_node == "rag_policy_node":
                    update = rag_policy_node(state)
                    state.update(update)

                # 3. Response synthesis
                update = response_synthesis_node(state)
                state.update(update)
                return state

        return NativeStateGraphRunner()


agent_graph = create_helpdesk_graph()


def run_agent(employee_id: str, query: str) -> Dict[str, Any]:
    """
    Convenience method to execute a query through the LangGraph agent pipeline.
    """
    initial_state: AgentState = {
        "employee_id": employee_id,
        "raw_query": query,
        "redacted_query": query,
        "detected_pii": [],
        "is_safe": True,
        "blocked_reason": None,
        "routed_domain": "HR_POLICY",
        "intent": None,
        "rag_result": None,
        "mcp_result": None,
        "final_response": "",
        "step_history": []
    }
    result = agent_graph.invoke(initial_state)
    return result
