import sqlite3
conn = sqlite3.connect("legal.db")
conn.execute("DELETE FROM templates;")
conn.commit()
conn.close()
