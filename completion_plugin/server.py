"""Optional MCP diagnostics. Approval remains a trusted host action."""
from mcp.server.fastmcp import FastMCP
from .editorial import review
app = FastMCP('completion-review-plugin')
@app.tool()
def capabilities() -> dict:
    return {'text':'deterministic diagnostics and review-only candidate comparison',
            'semantic_verification':'not_configured','native':'not_configured',
            'user_confirmation':'trusted_host_only','stop_installed':False}
@app.tool()
def review_text(text: str, profile: str = 'conversation_summary', candidate: str | None = None) -> dict:
    return review(text,profile,candidate=candidate)
if __name__=='__main__':app.run(transport='stdio')
