"""
app/main.py
===========
FastAPI Production Server for GoAified HR/IT Helpdesk AI Agent.
Endpoints:
- POST /chat: Process queries through LangGraph, MCP, RAG, and Guardrails.
- GET /health: Health check reporting status, LLM configuration, and database connectivity.
- GET /mcp/tools: List available MCP tools for inspection.
- GET /: Welcome and API overview.
"""

import os
import time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.graph import run_agent, gemini_llm
from app.mcp_server import AVAILABLE_TOOLS, db

# Initialize FastAPI App
app = FastAPI(
    title="GoAified HR/IT Helpdesk AI Agent",
    description=(
        "Production-ready AI Helpdesk Agent built with LangGraph, Google Gemini, "
        "RAG over company policy documents, and PostgreSQL connected via Model Context Protocol (MCP). "
        "Includes enterprise guardrails: Prompt-Injection Defense, PII Masking, and Topic Boundaries."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for frontend clients / dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TIME = time.time()


# =====================================================================
# Request / Response Schemas
# =====================================================================

class ChatRequest(BaseModel):
    employee_id: Optional[str] = Field(None, description="Employee identifier (e.g., EMP101, EMP001)")
    emp_id: Optional[str] = Field(None, description="Alias for employee_id (e.g., EMP101)")
    query: Optional[str] = Field(None, description="The user query")
    message: Optional[str] = Field(None, description="Alias for query")

    def get_employee_id(self) -> str:
        return self.employee_id or self.emp_id or "EMP101"

    def get_query(self) -> str:
        return self.query or self.message or ""


class ChatResponse(BaseModel):
    employee_id: str
    emp_id: str
    response: str
    answer: str
    sanitized_query: str
    blocked: bool
    is_safe: bool
    blocked_reason: Optional[str] = None
    routed_domain: str
    detected_pii: List[str]
    workflow_steps: List[str]
    sources: Optional[List[Dict[str, str]]] = None


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    llm_model: str
    database_mode: str
    guardrails_enabled: bool
    mcp_tools_count: int


# =====================================================================
# API Endpoints
# =====================================================================

@app.get("/", tags=["General"])
def root():
    return {
        "service": "GoAified HR/IT Helpdesk Agent",
        "status": "online",
        "documentation": "/docs",
        "health": "/health",
        "chat_endpoint": "POST /chat"
    }


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def health_check():
    """
    System health check returning database status and LLM readiness.
    """
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    db_mode = "PostgreSQL" if db.use_postgres else "SQLite (Local Fallback)"
    
    return HealthResponse(
        status="healthy",
        uptime_seconds=round(time.time() - START_TIME, 2),
        llm_model=model_name if gemini_llm else f"{model_name} (Deterministic Fallback Engine)",
        database_mode=db_mode,
        guardrails_enabled=True,
        mcp_tools_count=len(AVAILABLE_TOOLS)
    )


@app.post("/chat", response_model=ChatResponse, tags=["Agent Execution"])
def chat(request: ChatRequest):
    """
    Main conversational agent endpoint:
    - Passes input through Guardrails (PII redaction, injection detection, domain check).
    - Routes state to either Vector RAG or PostgreSQL MCP Tool.
    - Synthesizes final source-cited response.
    """
    user_query = request.get_query().strip()
    emp_id = request.get_employee_id().strip()

    if not user_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'query' or 'message' field cannot be empty."
        )

    try:
        agent_output = run_agent(
            employee_id=emp_id,
            query=user_query
        )

        sources = None
        if agent_output.get("rag_result") and "sources" in agent_output["rag_result"]:
            sources = agent_output["rag_result"]["sources"]

        is_safe = agent_output.get("is_safe", True)
        final_answer = agent_output.get("final_response", "")

        return ChatResponse(
            employee_id=emp_id,
            emp_id=emp_id,
            response=final_answer,
            answer=final_answer,
            sanitized_query=agent_output.get("redacted_query", user_query),
            blocked=not is_safe,
            is_safe=is_safe,
            blocked_reason=agent_output.get("blocked_reason"),
            routed_domain=agent_output.get("routed_domain", "UNKNOWN"),
            detected_pii=agent_output.get("detected_pii", []),
            workflow_steps=agent_output.get("step_history", []),
            sources=sources
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent workflow error: {str(e)}"
        )


@app.get("/mcp/tools", tags=["MCP Tools"])
def list_mcp_tools():
    """
    Inspect all Model Context Protocol (MCP) tools registered for PostgreSQL interaction.
    """
    tools = []
    for name, meta in AVAILABLE_TOOLS.items():
        tools.append({
            "name": name,
            "description": meta["description"],
            "schema": meta["parameters"]
        })
    return {"count": len(tools), "tools": tools}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
