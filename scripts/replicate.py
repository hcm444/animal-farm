import requests
import sqlite3
API_URL = "https://urchin-app-ihlrx.ondigitalocean.app/api/data"
DATABASE = "replicated.db"
POSTS_TABLE = "posts"
response = requests.get(API_URL)
print(response.text)
data = response.json()["data"]
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()
cursor.execute(f"CREATE TABLE IF NOT EXISTS {POSTS_TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, content TEXT, reply_id INTEGER, timestamp REAL)")
for row in data:
    _, username, content, reply_id, timestamp = row  # Exclude the first value (id column)
    cursor.execute(
        f"INSERT INTO {POSTS_TABLE} (username, content, reply_id, timestamp) VALUES (?, ?, ?, ?)",
        (username, content, reply_id, timestamp),
    )
conn.commit()
conn.close()
print("Database replication complete.")
