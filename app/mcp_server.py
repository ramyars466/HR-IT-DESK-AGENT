"""
app/mcp_server.py
=================
Model Context Protocol (MCP) Server connecting AI Agents to PostgreSQL.
Exposes database tools for:
- get_employee_leave_balance(employee_id)
- get_employee_profile(employee_id)
- get_it_tickets(employee_id)
- create_it_ticket(employee_id, issue_type, description, priority)

Features:
- Dual PostgreSQL and SQLite engine: seamlessly uses PostgreSQL when available;
  falls back to auto-seeded local SQLite db to allow zero-setup standalone execution.
- MCP Standard Protocol support (stdio JSON-RPC) & Direct Python Callable adapter for LangGraph.
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("helpdesk.mcp")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = DATA_DIR / "hr_it_helpdesk.db"
INIT_SQL_PATH = DATA_DIR / "init.sql"

DATABASE_URL = os.getenv("DATABASE_URL", "")


class DatabaseManager:
    """Manages connections to PostgreSQL or SQLite fallback with schema seeding."""
    def __init__(self):
        self.use_postgres = False
        self.pg_conn = None
        self._init_connection()

    def _init_connection(self):
        if DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://"):
            try:
                import psycopg2
                self.pg_conn = psycopg2.connect(DATABASE_URL)
                self.use_postgres = True
                logger.info("Successfully connected to PostgreSQL at %s", DATABASE_URL.split("@")[-1])
                return
            except Exception as e:
                logger.warning("PostgreSQL connection failed (%s). Falling back to local SQLite.", e)

        # Fallback to SQLite
        self.use_postgres = False
        self._ensure_sqlite_initialized()

    def _ensure_sqlite_initialized(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()

        # Check if employees table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees';")
        if not cursor.fetchone():
            logger.info("Initializing SQLite database with schema and seed data from %s", INIT_SQL_PATH)
            if INIT_SQL_PATH.exists():
                sql_script = INIT_SQL_PATH.read_text(encoding="utf-8")
                # Clean up postgres SERIAL syntax for SQLite compatibility
                sqlite_script = sql_script.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                cursor.executescript(sqlite_script)
                conn.commit()
            else:
                self._seed_minimal_sqlite(cursor)
                conn.commit()
        conn.close()

    def _seed_minimal_sqlite(self, cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                department TEXT NOT NULL,
                casual_leave_balance INTEGER NOT NULL DEFAULT 12,
                sick_leave_balance INTEGER NOT NULL DEFAULT 10,
                earned_leave_balance INTEGER NOT NULL DEFAULT 15,
                joining_date TEXT NOT NULL,
                manager_name TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS it_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                employee_id TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                priority TEXT NOT NULL DEFAULT 'MEDIUM',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO employees (id, employee_id, name, email, role, department, casual_leave_balance, sick_leave_balance, earned_leave_balance, joining_date, manager_name) VALUES 
            (1, 'EMP001', 'Rahul Sharma', 'rahul.sharma@company.com', 'AI Engineer Intern', 'AI Engineering', 8, 7, 12, '2026-06-01', 'Vikram Mehta'),
            (6, 'EMP101', 'Ramya RS', 'ramya.rs@company.com', 'AI Engineer', 'AI Engineering', 8, 5, 12, '2026-06-01', 'Vikram Mehta');
        """)

    def get_connection(self):
        if self.use_postgres and self.pg_conn and not self.pg_conn.closed:
            return self.pg_conn
        return sqlite3.connect(SQLITE_DB_PATH)


db = DatabaseManager()


# =====================================================================
# FastMCP Integration (Official MCP SDK)
# =====================================================================

try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("CompanyHelpdeskDB")
except Exception:
    class DummyMCP:
        def tool(self):
            return lambda f: f
        def run(self, **kwargs):
            pass
    mcp = DummyMCP()

@mcp.tool()
def get_leave_balance(emp_id: str) -> str:
    """Fetch remaining casual and sick leaves for a given employee ID."""
    res = get_employee_leave_balance(emp_id)
    if res.get("status") != "success":
        return f"No employee found with ID {emp_id}."
    lb = res["leave_balances"]
    return f"Employee {res['name']} ({emp_id}) has {lb['casual_leave']} casual leaves and {lb['sick_leave']} sick leaves remaining."

@mcp.tool()
def get_ticket_status(emp_id: str) -> str:
    """Check existing IT support tickets for an employee ID."""
    res = get_it_tickets(emp_id)
    if res.get("status") != "success" or not res.get("tickets"):
        return "No active IT tickets found."
    return str([(t["ticket_id"], t["description"], t["status"]) for t in res["tickets"]])

@mcp.tool()
def create_it_ticket_fastmcp(emp_id: str, issue: str) -> str:
    """Create a new IT support ticket in PostgreSQL."""
    res = create_it_ticket(emp_id, issue_type="IT Support", description=issue, priority="HIGH")
    if res.get("status") == "success":
        return f"Created IT ticket #{res.get('ticket_id')} for {emp_id}: '{issue}'."
    return f"Failed to create ticket: {res.get('message')}"


# =====================================================================
# MCP Tool Functions (Exposed to LangGraph and MCP Protocol)
# =====================================================================

def get_employee_leave_balance(employee_id: str) -> Dict[str, Any]:
    """
    Fetch the remaining casual, sick, and earned leave balances for a specific employee.
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT employee_id, name, department, role, casual_leave_balance, sick_leave_balance, earned_leave_balance FROM employees WHERE employee_id = ?"
        if db.use_postgres:
            query = query.replace("?", "%s")

        cursor.execute(query, (employee_id.strip(),))
        row = cursor.fetchone()
        if not row:
            return {
                "status": "error",
                "message": f"Employee with ID '{employee_id}' was not found in the database."
            }

        return {
            "status": "success",
            "employee_id": row[0],
            "name": row[1],
            "department": row[2],
            "role": row[3],
            "leave_balances": {
                "casual_leave": row[4],
                "sick_leave": row[5],
                "earned_leave": row[6],
                "total_available": row[4] + row[5] + row[6]
            }
        }
    finally:
        if not db.use_postgres:
            conn.close()


def get_employee_profile(employee_id: str) -> Dict[str, Any]:
    """
    Retrieve employee profile details including reporting manager and joining date.
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT employee_id, name, email, role, department, joining_date, manager_name FROM employees WHERE employee_id = ?"
        if db.use_postgres:
            query = query.replace("?", "%s")

        cursor.execute(query, (employee_id.strip(),))
        row = cursor.fetchone()
        if not row:
            return {"status": "error", "message": f"Employee '{employee_id}' not found."}

        return {
            "status": "success",
            "employee": {
                "employee_id": row[0],
                "name": row[1],
                "email": row[2],
                "role": row[3],
                "department": row[4],
                "joining_date": str(row[5]),
                "manager_name": row[6]
            }
        }
    finally:
        if not db.use_postgres:
            conn.close()


def get_it_tickets(employee_id: str) -> Dict[str, Any]:
    """
    Retrieve all open and past IT support tickets submitted by the employee.
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT ticket_id, issue_type, description, status, priority, created_at, updated_at FROM it_tickets WHERE employee_id = ? ORDER BY id DESC"
        if db.use_postgres:
            query = query.replace("?", "%s")

        cursor.execute(query, (employee_id.strip(),))
        rows = cursor.fetchall()

        tickets = []
        for r in rows:
            tickets.append({
                "ticket_id": r[0],
                "issue_type": r[1],
                "description": r[2],
                "status": r[3],
                "priority": r[4],
                "created_at": str(r[5]),
                "updated_at": str(r[6])
            })

        return {
            "status": "success",
            "employee_id": employee_id,
            "ticket_count": len(tickets),
            "tickets": tickets
        }
    finally:
        if not db.use_postgres:
            conn.close()


def create_it_ticket(employee_id: str, issue_type: str, description: str, priority: str = "MEDIUM") -> Dict[str, Any]:
    """
    Create a new IT Helpdesk ticket in PostgreSQL for hardware, software, or access requests.
    """
    conn = db.get_connection()
    cursor = conn.cursor()
    try:
        # Check employee exists
        check_q = "SELECT name FROM employees WHERE employee_id = ?"
        if db.use_postgres:
            check_q = check_q.replace("?", "%s")
        cursor.execute(check_q, (employee_id.strip(),))
        emp = cursor.fetchone()
        if not emp:
            return {"status": "error", "message": f"Cannot create ticket: Employee ID '{employee_id}' not found."}

        # Generate ticket ID
        cursor.execute("SELECT COUNT(*) FROM it_tickets")
        count = cursor.fetchone()[0]
        ticket_id = f"IT-{1000 + count + 1}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        insert_q = """
            INSERT INTO it_tickets (ticket_id, employee_id, issue_type, description, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
        """
        if db.use_postgres:
            insert_q = insert_q.replace("?", "%s")

        cursor.execute(insert_q, (
            ticket_id, employee_id.strip(), issue_type.strip(), description.strip(), priority.upper(), now_str, now_str
        ))
        conn.commit()

        logger.info("Created IT ticket %s for %s (%s)", ticket_id, employee_id, issue_type)
        return {
            "status": "success",
            "ticket_id": ticket_id,
            "employee_id": employee_id,
            "issue_type": issue_type,
            "priority": priority.upper(),
            "ticket_status": "OPEN",
            "created_at": now_str,
            "message": f"IT support ticket {ticket_id} has been raised successfully with {priority.upper()} priority."
        }
    finally:
        if not db.use_postgres:
            conn.close()


# =====================================================================
# MCP Server Tool Registry & JSON-RPC Protocol Handler
# =====================================================================

AVAILABLE_TOOLS = {
    "get_employee_leave_balance": {
        "function": get_employee_leave_balance,
        "description": "Fetch real-time casual, sick, and earned leave balances for an employee ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "Employee ID (e.g., EMP001)"}
            },
            "required": ["employee_id"]
        }
    },
    "get_employee_profile": {
        "function": get_employee_profile,
        "description": "Retrieve employee information, manager, and department details.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "Employee ID (e.g., EMP001)"}
            },
            "required": ["employee_id"]
        }
    },
    "get_it_tickets": {
        "function": get_it_tickets,
        "description": "Get status of all IT support tickets for a specific employee.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "Employee ID (e.g., EMP001)"}
            },
            "required": ["employee_id"]
        }
    },
    "create_it_ticket": {
        "function": create_it_ticket,
        "description": "Raise a new IT support ticket in PostgreSQL for hardware, software, VPN, or access issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "Employee ID (e.g., EMP001)"},
                "issue_type": {"type": "string", "description": "Category: Hardware Defect, VPN, Software Access, etc."},
                "description": {"type": "string", "description": "Detailed description of the issue or hardware symptom"},
                "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "default": "MEDIUM"}
            },
            "required": ["employee_id", "issue_type", "description"]
        }
    }
}


def handle_mcp_request(json_rpc_str: str) -> str:
    """Standard JSON-RPC 2.0 processor for Model Context Protocol (MCP) clients."""
    try:
        req = json.loads(json_rpc_str)
        method = req.get("method")
        msg_id = req.get("id")

        if method == "tools/list":
            tools_list = [
                {
                    "name": name,
                    "description": meta["description"],
                    "inputSchema": meta["parameters"]
                }
                for name, meta in AVAILABLE_TOOLS.items()
            ]
            return json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}})

        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})

            if name in AVAILABLE_TOOLS:
                tool_func = AVAILABLE_TOOLS[name]["function"]
                result = tool_func(**arguments)
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                    }
                })
            else:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool '{name}' not found."}
                })

        return json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32600, "message": "Invalid Request"}})
    except Exception as e:
        return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(e)}})


if __name__ == "__main__":
    # If invoked directly, run MCP stdio loop
    logger.info("Starting PostgreSQL MCP Server over stdio...")
    for line in sys.stdin:
        if line.strip():
            sys.stdout.write(handle_mcp_request(line.strip()) + "\n")
            sys.stdout.flush()
