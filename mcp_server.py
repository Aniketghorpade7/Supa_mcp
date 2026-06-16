import os
import sys
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from fastmcp import FastMCP

SUPABASE_DB_URL = os.environ.get("SUPABASE_DATABASE_URL")
ROUTING_KEY = os.environ.get("MCP_SECRET_PASSKEY")

if not SUPABASE_DB_URL or not ROUTING_KEY:
    print("CRITICAL CONFIGURATION ERROR: Missing environment variables!", file=sys.stderr)
    sys.exit(1)

# Initialize FastMCP cleanly with zero strict transport-level auth blocking
mcp = FastMCP("Agency Marketing Gateway")

# Initialize a thread-safe connection pool for stable web hosting performance
db_pool = SimpleConnectionPool(1, 10, SUPABASE_DB_URL)

# =====================================================================
# TOOL 1: THE QUEUE QUERY (Synchronous execution pattern)
# =====================================================================
@mcp.tool()
def fetch_pending_reviews(routing_id: str) -> str:
    """
    Retrieves entries from the data table that match the review stage criteria.
    You must pass your unique project routing_id string to fetch the rows.
    """
    if routing_id != ROUTING_KEY:
        return "ERROR: Access Denied. The routing configuration string is invalid."

    conn = db_pool.getconn()
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
            return "The review queue is clear. No posts are waiting for human approval."
            
        output = "MARKETING ENTRIES AWAITING HUMAN INTERVENTION:\n" + "="*50 + "\n"
        for row in rows:
            output += f" [POST ID: {row[0]}]\n"
            output += f"   • Layout Type: {row[2] if row[2] else 'Not Specified'}\n"
            output += f"   • Cloud Media Resource: {row[1]}\n"
            output += "-"*50 + "\n"
        return output
    except Exception as e:
        return f"Database Connection Error: {str(e)}"
    finally:
        cur.close()
        db_pool.putconn(conn)

# =====================================================================
# TOOL 2: THE HUMAN GATEKEEPER (Synchronous execution pattern)
# =====================================================================
@mcp.tool()
def commit_human_approved_post(
    post_id: int, 
    routing_id: str,
    final_caption: str = None,   
    final_hashtags: str = None,  
    final_post_type: str = None  
) -> str:
    """
    Updates the execution metrics and moves the status of an entry forward.
    You must pass your unique project routing_id string to write changes.
    """
    if routing_id != ROUTING_KEY:
        return "ERROR: Access Denied. The routing configuration string is invalid."

    conn = db_pool.getconn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT campaign_status FROM social_campaigns WHERE id = %s;", (post_id,))
        record = cur.fetchone()
        
        if not record:
            return f"Execution Aborted: Post ID {post_id} does not exist."
        if record[0] != 'AWAITING_REVIEW':
            return f"Execution Aborted: Post ID {post_id} is in a '{record[0]}' state, not 'AWAITING_REVIEW'."

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
        return f"SUCCESS: Post ID {post_id} is marked 'READY'."
    except Exception as e:
        conn.rollback()
        return f"Transaction Error: State update rolled back -> {str(e)}"
    finally:
        cur.close()
        db_pool.putconn(conn)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
