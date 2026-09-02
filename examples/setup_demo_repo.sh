#!/usr/bin/env bash
# Builds a throwaway git repo at /tmp/pr-agent-demo with a "before" commit
# and an "after" commit that introduces a few deliberate issues, so you can
# test the agent immediately with no real project needed.
set -e

DEMO_DIR="/tmp/pr-agent-demo"
rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Test"

cat > app.py <<'PYEOF'
import sqlite3


def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def list_users():
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    return cur.fetchall()
PYEOF
git add app.py
git commit -q -m "before: safe baseline"

cat > app.py <<'PYEOF'
import sqlite3

API_KEY = "sk-live-4f8a9b2c1d3e4f5a6b7c8d9e0f1a2b3c"


def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # BUG: string-concatenated query, user_id is attacker-controlled
    query = "SELECT * FROM users WHERE id = " + user_id
    cur.execute(query)
    return cur.fetchone()


def list_users():
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    return cur.fetchall()


def delete_all_users():
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM users")
    conn.commit()
    # no error handling, no confirmation, no auth check
PYEOF
git add app.py
git commit -q -m "after: adds SQL injection, hardcoded key, unguarded delete"

echo "Demo repo created at $DEMO_DIR"
echo "Now run:"
echo "  cd $DEMO_DIR"
echo "  export ANTHROPIC_API_KEY=sk-ant-..."
echo "  python /home/claude/pr-security-agent/test_local.py"
