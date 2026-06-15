import os
import sys
import psycopg2
from fastmcp import FastMCP, Context

# Initialize FastMCP Server over web pathways
mcp = FastMCP(
    "Agency Marketing Gateway",
    title="Secure Marketing Automation Controller",
    description="Isolated database tools for semi-autonomous content publishing"
)

# Extract your secure environment tokens from your cloud hosting space
SERVER_AUTH_TOKEN = os.environ.get("MCP_SECRET_PASSKEY")
SUPABASE_DB_URL = os.environ.get("SUPABASE_DATABASE_URL")

# Guardrail check to prevent silent container crashes during hosting boot
if not SERVER_AUTH_TOKEN or not SUPABASE_DB_URL:
    print("CRITICAL CONFIGURATION ERROR: Missing environment variables!", file=sys.stderr)
    sys.exit(1)

def get_db_connection():
    """Establishes a connection to your Supabase PostgreSQL cluster using the URI key."""
    return psycopg2.connect(SUPABASE_DB_URL)

def authenticate_session(ctx: Context) -> bool:
    """Verifies that incoming Claude requests provide your exact secret passphrase."""
    auth_header = ctx.request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    return auth_header.split(" ")[1] == SERVER_AUTH_TOKEN

# =====================================================================
# TOOL 1: THE FILTERED QUEUE QUERY
# =====================================================================
@mcp.tool()
async def fetch_pending_reviews(ctx: Context) -> str:
    """
    Fetches a list of all raw marketing entries currently waiting for content generation and review.
    Use this tool to see what needs captions and hashtags today.
    """
    if not authenticate_session(ctx):
        return "❌ SECURITY ERROR: Unauthorized access. The security passkey is invalid."
        
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
            return "🎉 The review queue is perfectly clear! There are no posts waiting for human approval."
            
        output = "📋 MARKETING ENTRIES AWAITING HUMAN INTERVENTION:\n" + "="*50 + "\n"
        for row in rows:
            output += f"🔹 [POST ID: {row[0]}]\n"
            output += f"   • Layout Type: {row[2] if row[2] else 'Not Specified'}\n"
            output += f"   • Cloud Media Resource: {row[1]}\n"
            output += "-"*50 + "\n"
            
        return output
    except Exception as e:
        return f"❌ Database Communication Failure: {str(e)}"
    finally:
        cur.close()
        conn.close()

# =====================================================================
# TOOL 2: THE HUMAN GATEKEEPER (Handles full metadata or blank payloads)
# =====================================================================
@mcp.tool()
async def commit_human_approved_post(
    post_id: int, 
    ctx: Context,
    final_caption: str = None,   
    final_hashtags: str = None,  
    final_post_type: str = None  
) -> str:
    """
    Saves the verified content metadata to the database and marks the post as READY.
    CRITICAL RULE: Only execute this tool if the human operator explicitly instructs you to.
    You can leave the caption, hashtags, and post_type empty if the human wants a raw media post.
    """
    if not authenticate_session(ctx):
        return "❌ SECURITY ERROR: Unauthorized access. The security passkey is invalid."
        
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT campaign_status FROM social_campaigns WHERE id = %s;", (post_id,))
        record = cur.fetchone()
        
        if not record:
            return f"❌ Execution Aborted: Post ID {post_id} does not exist."
        if record[0] != 'AWAITING_REVIEW':
            return f"❌ Execution Aborted: Post ID {post_id} is in a '{record[0]}' state, not 'AWAITING_REVIEW'."

        # Overwrite content text strings while pushing status instantly to READY
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
        return f"✅ SUCCESS: Post ID {post_id} is marked 'READY'. The cloud cron will deploy the media URL."
        
    except Exception as e:
        conn.rollback()
        return f"❌ Transaction Error: State update rolled back -> {str(e)}"
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    # Configures FastMCP to launch over native Streamable HTTP on Render's dynamic portal port
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))