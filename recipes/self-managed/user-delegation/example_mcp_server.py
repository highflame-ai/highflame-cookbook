"""A small example MCP server that Highflame does not know about.

`strands_direct_mcp_llm_gateway.ipynb` starts it on your machine, and the agent calls it directly,
not through the Highflame MCP gateway. Its data is made up.

    python example_mcp_server.py     # serves http://127.0.0.1:8099/mcp
"""

import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("acme-crm")

CUSTOMERS = [
    {"id": "C-1001", "name": "Northwind Labs", "email": "ops@northwind.example", "phone": "+1-555-0101"},
    {"id": "C-1002", "name": "Contoso Bio", "email": "it@contoso.example", "phone": "+1-555-0102"},
    {"id": "C-1003", "name": "Fabrikam Health", "email": "admin@fabrikam.example", "phone": "+1-555-0103"},
]


@server.tool()
def search_customers(query: str) -> str:
    """Find customers by name. Returns ids and names only."""
    hits = [c for c in CUSTOMERS if query.lower() in c["name"].lower()]
    return "\n".join(f'{c["id"]} {c["name"]}' for c in hits) or "no match"


@server.tool()
def export_customers() -> str:
    """Export every customer record, with email addresses and phone numbers."""
    return "\n".join(f'{c["id"]},{c["name"]},{c["email"]},{c["phone"]}' for c in CUSTOMERS)


if __name__ == "__main__":
    server.run("streamable-http", host="127.0.0.1", port=int(os.environ.get("EXAMPLE_MCP_PORT", "8099")))
