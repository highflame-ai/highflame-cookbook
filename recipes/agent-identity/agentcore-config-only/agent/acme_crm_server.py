"""A small MCP server that Highflame does not know about. Its data is made up.

The agent starts it inside the AgentCore runtime and talks to it over stdio, so there is no MCP
gateway in between. Highflame still sees each tool call the model asks for, at the LLM gateway.
"""

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
    server.run("stdio")
