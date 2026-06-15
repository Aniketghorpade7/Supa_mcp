import os
import psycopg2
from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import INVALID_PARAMS

# Initialize FastMCP Server with HTTP/SSE capabilities
mcp = FastMCP("Agency Marketing Database Hub")

# Secret token you create to protect your server from public intruders
SERVER_AUTH_TOKEN = os.environ.get("MCP_SECRET_PASSKEY", "my_super_secret_key_123")

def get_db_connection():
    """Establishes a connection to your Supabase PostgreSQL cluster."""
    return psycopg2.connect(os.environ["SUPABASE_DATABASE_URL"])

def verify_token(context):
    """Ensures incoming Claude requests provide your private passkey."""
    # FastMCP automatically surfaces request headers inside the context
    headers = context.request_context.headers if context.request_context else {}
    auth_header = headers.get("authorization", "")
    
    if not auth_header.startswith("Bearer ") or auth_header.split(" ")[1] != SERVER_AUTH_TOKEN:
        raise McpError(INVALID_PARAMS, "Unauthorized access: Invalid or missing API passkey.")

@mcp.tool()
async def fetch_pending_reviews(ctx) -> str:
    """Fetches all campaigns currently waiting for captions and hashtags verification."""
    verify_token(ctx)
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, media_url, post_type, campaign_status 
            FROM social_campaigns 
            WHERE campaign_status = 'AWAITING_REVIEW';
            """
        )
        rows = cur.fetchall()
        if not rows:
            return "🎉 The review queue is currently empty! No posts are pending action."
        
        output = "📋 CURRENT PENDING QUEUE:\n" + "="*40 + "\n"
        for row in rows:
            output += f"🔹 [ID: {row[0]}] | Type: {row[2]} | Status: {row[3]}\n🔗 Media Asset Link: {row[1]}\n"
            output += "-"*40 + "\n"
        return output
    except Exception as e:
        return f"❌ Database operational failure: {str(e)}"
    finally:
        cur.close()
        conn.close()

@mcp.tool()
async def verify_and_ready_post(post_id: int, approved_caption: str, approved_hashtags: str, ctx) -> str:
    """Updates a post with its finalized text, scheduling date, and flips status to READY for publishing."""
    verify_token(ctx)
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE social_campaigns 
            SET caption = %s, hashtags = %s, campaign_status = 'READY', posting_date = CURRENT_DATE
            WHERE id = %s;
            """,
            (approved_caption, approved_hashtags, post_id)
        )
        conn.commit()
        return f"✅ Success! Post ID {post_id} has been fully updated and marked 'READY'. The cloud cron job will handle transmission automatically."
    except Exception as e:
        conn.rollback()
        return f"❌ Transaction rolled back due to error: {str(e)}"
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    # Runs the server using the streamable HTTP/SSE transport layer
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))