'''
This file consists of functions that are considered helpers.
They are called in app.py.
'''

import re
import sqlite3
import secrets
import hashlib

# SQLite database configuration
DATABASE = "users.db"
USERS_TABLE = "users"
POSTS_TABLE = "posts"
USERS_LAST_POST_TABLE = "users_last_post"
THREADS_PER_PAGE = 10
MAX_POSTS = 1000
MAX_POSTS_PER_THREAD = 10
POST_CHARS_LIMIT = 500
COOL_DOWN_TIME = 30

# Validate email format
def validate_email(email):
    pattern = r"[^@]+@[^@]+\.[^@]+"
    if re.match(pattern, email):
        return True
    else:
        return False
    
# create the users last post table
def create_users_last_post_table():
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {USERS_LAST_POST_TABLE} (username TEXT PRIMARY KEY, last_post_time REAL)"
        )

# create the users table    
def create_users_table():    
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {USERS_TABLE} (username TEXT(20) PRIMARY KEY, password TEXT, email TEXT, ip_address TEXT)"
        )
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {POSTS_TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, content TEXT, reply_id INTEGER, timestamp REAL)"
        )

def extract_reply_id(content):
    match = re.search(r">>(\d+)", content)
    if match:
        return int(match.group(1))
    else:
        return None
    
def build_thread(posts):
    thread_map = {}
    root_posts = []
    post_map = {}

    for post_id, username, content, reply_id, timestamp in posts:
        post_map[post_id] = {
            "post_id": post_id,
            "username": username,
            "content": content,
            "children": [],
            "timestamp": timestamp,
        }

        if reply_id is None:
            root_posts.append(post_id)
        else:
            if reply_id in thread_map:
                thread_map[reply_id].append(post_id)
            else:
                thread_map[reply_id] = [post_id]

    def build_recursive(post_id):
        post_data = post_map[post_id]
        children = thread_map.get(post_id, [])

        sorted_children = sorted(children)  # Sort children based on post ID

        for child_id in sorted_children:
            child_data = post_map[child_id]
            post_data["children"].append(build_recursive(child_id))

        return post_data

    threads = []
    for root_id in root_posts:
        threads.append(build_recursive(root_id))

    return threads

# helper to hash and scramble ip
def get_hashed_ip_address(ip_address):
    salt = secrets.token_hex(16)
    salted_ip = ip_address + salt
    return hashlib.sha512(salted_ip.encode()).hexdigest()
