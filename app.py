from flask import Flask, render_template, request, redirect, url_for, session, flash, session
from helpers import get_hashed_ip_address, build_thread, validate_email, create_users_last_post_table, create_users_table, extract_reply_id, DATABASE, USERS_TABLE, POSTS_TABLE, USERS_LAST_POST_TABLE, THREADS_PER_PAGE, MAX_POSTS, MAX_POSTS_PER_THREAD, POST_CHARS_LIMIT, COOL_DOWN_TIME
import sqlite3
import hashlib
import re
from flask_caching import Cache
from datetime import datetime
import math

app = Flask(__name__)
cache = Cache(app)
app.secret_key = "your-secret-key"

# Create the users_last_post table if it doesn't exist
create_users_last_post_table()
# Create the user_table table if it doesn't exist
create_users_table()


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
                last_post_time_str = result[0]
                last_post_time = datetime.strptime(last_post_time_str, "%Y-%m-%d %H:%M:%S")
                current_time = datetime.now()
                cooldown_period = COOL_DOWN_TIME

                time_since_last_post = current_time - last_post_time
                if cooldown_period > 0 and time_since_last_post.total_seconds() < cooldown_period:
                    remaining_time = cooldown_period - time_since_last_post
                    flash(f"You can only post once every 30 seconds. Please wait {int(remaining_time)} seconds.")

            # Update the last post time for the user
            current_time = datetime.now()
            current_time = current_time.replace(microsecond=0)  # Drop milliseconds
            current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                f"REPLACE INTO {USERS_LAST_POST_TABLE} (username, last_post_time) VALUES (?, ?)",
                (username, current_time_str),
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
                flash("Post already exists")
            utc_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
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
        error_flag = False
        # Need to make sure len is not None
        if username is not None and len(username) > 20:
            flash("Username cannot exceed 20 characters")
            error_flag = True
        if email is not None and not validate_email(email):
            flash("Email format invalid")
            error_flag = True
        
        if error_flag:
            return redirect(url_for("register"))
        
        '''
        Password requirments:
        - 10 chars long
        - at least one uppercase
        - at least one lowercase
        - at least one digit
        - at least one special char
        '''
        if (
            # Need to check for None again
            password is None or len(password) < 10
            or not re.search(r"\d", password)
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"[!@#$%^&*()\-_=+{};:,<.>]", password)
        ):
            # redirect if requirements are not met
            flash("""Your password does not meet the following requirements:\n- 10 characters or greater\n- At least one lowercase letter\n- At least one uppercase letter\n- At least one number\n- At least one special character""")
            return redirect(url_for("register"))
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.cursor()

            cursor.execute(
                f"SELECT * FROM {USERS_TABLE} WHERE email=?", (email,)
            )
            existing_user = cursor.fetchone()
            if existing_user:
                flash("Email already exists")
                return redirect(url_for("register"))

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
                flash("Invalid username or password")
                return redirect(url_for("index"))

            stored_password = result[0]

            hashed_password = hashlib.sha256(password.encode()).hexdigest()

            if stored_password == hashed_password:
                session["username"] = username

                # Get the client's IP address
                ip_address = request.remote_addr

                # Save the IP address in the database and hash it
                cursor.execute(
                    f"UPDATE {USERS_TABLE} SET ip_address=? WHERE username=?",
                    (get_hashed_ip_address(ip_address), username),
                )
                connection.commit()

                return redirect(url_for("index"))
            else:
                flash("Invalid username or password")
                return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)