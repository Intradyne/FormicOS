import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in c.fetchall()]
print("Tables:", tables)
for t in tables:
    c.execute("SELECT * FROM " + t + " LIMIT 5")
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    if rows:
        print("--- " + t + " (" + str(cols) + ") ---")
        for r in rows:
            print(r)
conn.close()
