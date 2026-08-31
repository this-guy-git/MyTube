import sqlite3

DB_FILE = "mytube.db"


def init_db():
    con = sqlite3.connect(DB_FILE)

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)

    con.commit()
    con.close()

    print(f"Database initialized: {DB_FILE}")


if __name__ == "__main__":
    init_db()