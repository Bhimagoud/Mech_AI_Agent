from fastmcp import FastMCP

# Initialize the MCP Server
mcp = FastMCP("Mech_AI_Agents_MCP")

@mcp.tool()
def ping() -> str:
    """A simple ping tool to verify the MCP server is running."""
    return "Pong! The Mech AI Agents MCP Server is active."

if __name__ == "__main__":
    # You can run this directly, or via fastmcp dev / fastmcp run
    mcp.run(transport="stdio")
