import sqlite3

DB_FILE = "mytube.db"


def init_db():
    user = input("User to modify: ").strip()

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    cur.execute(
        "SELECT role FROM users WHERE username = ?",
        (user,)
    )

    result = cur.fetchone()

    if result is None:
        print(f"User '{user}' does not exist!")
        con.close()
        return

    role = result[0]

    if role == "admin":
        remove = input(
            f"User '{user}' is already an admin. Remove admin status? (y/n): "
        ).strip().lower()

        if remove == "y":
            cur.execute(
                "UPDATE users SET role = 'user' WHERE username = ?",
                (user,)
            )
            con.commit()
            print(f"Admin status removed from '{user}'.")
        else:
            print(f"'{user}' will remain an admin.")

    else:
        cur.execute(
            "UPDATE users SET role = 'admin' WHERE username = ?",
            (user,)
        )
        con.commit()
        print(f"User '{user}' is now an admin.")

    con.close()


if __name__ == "__main__":
    init_db()