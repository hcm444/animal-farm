from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import hashlib
import re
import time
from flask_caching import Cache
import datetime
import math

app = Flask(__name__)
cache = Cache(app)
app.secret_key = "your-secret-key"

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


def create_users_last_post_table():
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS {USERS_LAST_POST_TABLE} (username TEXT PRIMARY KEY, last_post_time REAL)"
        )


# Create the users_last_post table if it doesn't exist
create_users_last_post_table()


def extract_reply_id(content):
    match = re.search(r">>(\d+)", content)
    if match:
        return int(match.group(1))
    else:
        return None


# Create the users table if it doesn't exist
with sqlite3.connect(DATABASE) as connection:
    cursor = connection.cursor()
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {USERS_TABLE} (username TEXT(20) PRIMARY KEY, password TEXT, email TEXT, ip_address TEXT)"
    )
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {POSTS_TABLE} (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, content TEXT, reply_id INTEGER, timestamp REAL)"
    )


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





@app.route("/about")
@cache.cached(timeout=60)  # Cache the about page for 60 seconds
def about():
    if "username" in session:
        return render_template("about.html")
    else:
        return redirect(url_for("login"))


@app.route("/")
@cache.cached(timeout=60)
def index():
    if "username" in session:
        # Fetch all posts from the database
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {POSTS_TABLE} ORDER BY id")
            posts = cursor.fetchall()

        threads = build_thread(posts)

        # Calculate the total number of pages based on the number of threads per page
        total_pages = math.ceil(len(threads) / THREADS_PER_PAGE)

        # Get the requested page number from the query parameters
        page = int(request.args.get("page", 1))

        # Calculate the starting and ending indices for the subset of threads
        start_index = (page - 1) * THREADS_PER_PAGE
        end_index = start_index + THREADS_PER_PAGE

        # Get the subset of threads for the current page
        paginated_threads = threads[start_index:end_index]

        return render_template(
            "index.html",
            threads=paginated_threads,
            total_pages=total_pages,
            current_page=page,
        )
    else:
        return redirect(url_for("login"))


@app.route("/post", methods=["POST"])
def post():
    if "username" in session:
        username = session["username"]
        content = request.form.get("content")
        reply_id = extract_reply_id(content)

        # Check if content exceeds 500 characters
        if len(content) > POST_CHARS_LIMIT:
            return "Post cannot exceed 500 characters."

        # Check if the reply ID is valid
        if reply_id is not None:
            with sqlite3.connect(DATABASE) as connection:
                cursor = connection.cursor()
                while True:
                    cursor.execute(
                        f"SELECT id, reply_id FROM {POSTS_TABLE} WHERE id=?", (reply_id,)
                    )
                    result = cursor.fetchone()
                    if result is None:
                        return "Invalid reply ID. The referenced post does not exist."
                    elif result[1] is None:
                        # Found the original post, break the loop
                        break
                    else:
                        # Update reply_id to reference the original post
                        reply_id = result[1]

        # Check if the thread has reached the maximum number of posts
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT COUNT(*) FROM {POSTS_TABLE} WHERE reply_id=?", (reply_id,)
            )
            post_count = cursor.fetchone()[0]

            if post_count >= MAX_POSTS_PER_THREAD:
                return "The thread has reached the maximum number of posts."

        # Check if the user has posted recently
        with sqlite3.connect(DATABASE) as connection:

            cursor = connection.cursor()
            cursor.execute(
                f"SELECT last_post_time FROM {USERS_LAST_POST_TABLE} WHERE username=?", (username,)
            )
            result = cursor.fetchone()
            if result is not None:
                last_post_time = result[0]
                current_time = time.time()
                cooldown_period = COOL_DOWN_TIME

                time_since_last_post = current_time - last_post_time
                if time_since_last_post < cooldown_period:
                    remaining_time = cooldown_period - time_since_last_post
                    return f"You can only post once every 30 seconds. Please wait {int(remaining_time)} seconds."

            # Update the last post time for the user
            current_time = time.time()
            cursor.execute(
                f"REPLACE INTO {USERS_LAST_POST_TABLE} (username, last_post_time) VALUES (?, ?)",
                (username, current_time),
            )
            connection.commit()

            # Proceed to insert the new post
            cursor.execute(
                f"SELECT COUNT(*) FROM {POSTS_TABLE}"
            )
            post_count = cursor.fetchone()[0]

            if post_count >= MAX_POSTS:
                # Fetch the oldest post and delete it
                cursor.execute(
                    f"SELECT MIN(id) FROM {POSTS_TABLE}"
                )
                oldest_post_id = cursor.fetchone()[0]
                cursor.execute(
                    f"DELETE FROM {POSTS_TABLE} WHERE id=?", (oldest_post_id,)
                )

            cursor.execute(
                f"SELECT * FROM {POSTS_TABLE} WHERE username=? AND content=?",
                (username, content),
            )
            existing_post = cursor.fetchone()
            if existing_post:
                return "Post already exists"
            utc_timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                f"INSERT INTO {POSTS_TABLE} (username, content, reply_id, timestamp) VALUES (?, ?, ?, ?)",
                (username, content, reply_id, utc_timestamp),
            )
            connection.commit()

        return redirect(url_for("index"))
    else:
        return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    elif request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        if len(username) > 20:
            return "Username cannot exceed 20 characters."
        # Validate email format and other form fields if needed

        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.cursor()

            cursor.execute(
                f"SELECT * FROM {USERS_TABLE} WHERE email=?", (email,)
            )
            existing_user = cursor.fetchone()
            if existing_user:
                return "Email already exists"

            cursor.execute(
                f"INSERT INTO {USERS_TABLE} (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password),
            )
            connection.commit()

        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    elif request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT password FROM {USERS_TABLE} WHERE username=?", (username,)
            )
            result = cursor.fetchone()

            if result is None:
                return "Invalid username or password"

            stored_password = result[0]

            hashed_password = hashlib.sha256(password.encode()).hexdigest()

            if stored_password == hashed_password:
                session["username"] = username

                # Get the client's IP address
                ip_address = request.remote_addr

                # Save the IP address in the database
                cursor.execute(
                    f"UPDATE {USERS_TABLE} SET ip_address=? WHERE username=?",
                    (ip_address, username),
                )
                connection.commit()

                return redirect(url_for("index"))
            else:
                return "Invalid username or password"


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
