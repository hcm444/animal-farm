import requests
import sqlite3

API_URL = "https://urchin-app-ihlrx.ondigitalocean.app/api/data"
DATABASE = "users.db"

response = requests.get(API_URL)
data = response.json()

# Fetch the data from the API response
posts_data = data["posts_data"]
last_post_data = data["last_post_data"]
users_data = data["users_data"]

# Establish a connection to the local database
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Create the necessary tables in the local database if they don't exist
cursor.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, content TEXT, reply_id INTEGER, timestamp REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS users_last_post (username TEXT PRIMARY KEY, last_post_time TIMESTAMP)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT(20) PRIMARY KEY, password TEXT, email TEXT, ip_address TEXT)")

# Insert the data into the local database
for row in posts_data:
    post_id, username, content, reply_id, timestamp = row
    cursor.execute("INSERT INTO posts (id, username, content, reply_id, timestamp) VALUES (?, ?, ?, ?, ?)", (post_id, username, content, reply_id, timestamp))

for row in last_post_data:
    username, last_post_time = row
    cursor.execute("INSERT INTO users_last_post (username, last_post_time) VALUES (?, ?)", (username, last_post_time))

for row in users_data:
    username, _, _, _ = row
    cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))

# Commit the changes and close the database connection
conn.commit()
conn.close()

print("Database replication complete.")
