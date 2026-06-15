import os
import sys
import psycopg2
from fastmcp import FastMCP

# Extract your database credentials from Render environment variables
SUPABASE_DB_URL = os.environ.get("SUPABASE_DATABASE_URL")
SERVER_AUTH_TOKEN = os.environ.get("MCP_SECRET_PASSKEY")

if not SUPABASE_DB_URL or not SERVER_AUTH_TOKEN:
    print("CRITICAL CONFIGURATION ERROR: Missing environment variables!", file=sys.stderr)
    sys.exit(1)

# Initialize FastMCP cleanly with zero strict transport-level auth blocking
mcp = FastMCP("Agency Marketing Gateway")

def get_db_connection():
    """Establishes a connection to your Supabase PostgreSQL cluster."""
    return psycopg2.connect(SUPABASE_DB_URL)

# =====================================================================
# TOOL 1: THE QUEUE QUERY (Protected by Passkey Verification)
# =====================================================================
@mcp.tool()
async def fetch_pending_reviews(security_passkey: str) -> str:
    """
    Fetches a list of all raw marketing entries currently waiting for review.
    You must provide the user's explicit security_passkey parameter to authorize the database query.
    """
    if security_passkey != SERVER_AUTH_TOKEN:
        return "❌ SECURITY ERROR: Unauthorized access. The provided security passkey is invalid."

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, media_url, post_type 
            FROM social_campaigns 
            WHERE campaign_status = 'AWAITING_REVIEW'
            ORDER BY created_at ASC;
            """
        )
        rows = cur.fetchall()
        if not rows:
            return "🎉 The review queue is clear! No posts are waiting for human approval."
            
        output = "📋 MARKETING ENTRIES AWAITING HUMAN INTERVENTION:\n" + "="*50 + "\n"
        for row in rows:
            output += f"🔹 [POST ID: {row[0]}]\n"
            output += f"   • Layout Type: {row[2] if row[2] else 'Not Specified'}\n"
            output += f"   • Cloud Media Resource: {row[1]}\n"
            output += "-"*50 + "\n"
        return output
    except Exception as e:
        return f"❌ Database Failure: {str(e)}"
    finally:
        cur.close()
        conn.close()

# =====================================================================
# TOOL 2: THE HUMAN GATEKEEPER (Protected by Passkey Verification)
# =====================================================================
@mcp.tool()
async def commit_human_approved_post(
    post_id: int, 
    security_passkey: str,
    final_caption: str = None,   
    final_hashtags: str = None,  
    final_post_type: str = None  
) -> str:
    """
    Saves the verified metadata and marks the post as READY.
    You must provide the user's explicit security_passkey parameter to authorize this update action.
    """
    if security_passkey != SERVER_AUTH_TOKEN:
        return "❌ SECURITY ERROR: Unauthorized access. The provided security passkey is invalid."

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT campaign_status FROM social_campaigns WHERE id = %s;", (post_id,))
        record = cur.fetchone()
        
        if not record:
            return f"❌ Execution Aborted: Post ID {post_id} does not exist."
        if record[0] != 'AWAITING_REVIEW':
            return f"❌ Execution Aborted: Post ID {post_id} is in a '{record[0]}' state, not 'AWAITING_REVIEW'."

        cur.execute(
            """
            UPDATE social_campaigns 
            SET caption = %s, 
                hashtags = %s, 
                post_type = %s,
                campaign_status = 'READY', 
                posting_date = CURRENT_DATE
            WHERE id = %s;
            """,
            (final_caption, final_hashtags, final_post_type, post_id)
        )
        conn.commit()
        return f"✅ SUCCESS: Post ID {post_id} is marked 'READY'."
    except Exception as e:
        conn.rollback()
        return f"❌ Transaction Error: State update rolled back -> {str(e)}"
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
