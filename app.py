import os
import json
import random
import string
from glob import glob
from urllib.parse import unquote
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps
from flask import abort
from bs4 import BeautifulSoup
import bleach
import markupsafe
from markupsafe import escape, Markup

ALLOWED_TAGS = ['b', 'em', 'u', 'strong', 'br']

def sanitize(text):
    return bleach.clean(text, tags=ALLOWED_TAGS, strip=True)

DEV_USERS = {'this guy', 'F87', 'TDot', 'thisguy0', 'f87', 'tdot'}
OG_USERS = {'this guy', 'F87', 'TDot', 'thisguy0', 'f87', 'tdot', 'ChanTanDingo', 'Fosh', 'hello', 'BigNiggaBalls'}
SOG_USERS = {'F87', 'TDot', 'f87', 'tdot'}


app = Flask(__name__)
app.secret_key = "CHANGE-THIS!!!"
# Folders configuration
UPLOAD_FOLDER = 'uploads'
TEMPLATE_FOLDER = 'templates'  # generated video pages will be saved here
VIDEOS_HTML_PATH = os.path.join(TEMPLATE_FOLDER, 'videos.html')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB limit for compensation

# Ensure required folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)






# Check for mainenance
mm=0
@app.before_request
def check():
    if mm == 1:
        abort(503)
@app.errorhandler(503)
def under(e):
    return render_template('maintenance.html')

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_dev_users():
    return {
        'DEV_USERS': DEV_USERS,
        'OG_USERS': OG_USERS,
        'SOG_USERS': SOG_USERS
    }


@app.route("/admin")
@admin_required
def admin_panel():
    files = [f for f in os.listdir("templates") if f.startswith("Mt-") and f.endswith(".html")]

    try:
        with open("takedowns.json", "r") as f:
            taken_down = json.load(f)
    except FileNotFoundError:
        taken_down = []

    videos_data = []
    for file in files:
        path = os.path.join("templates", file)
        with open(path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

            # Get video src
            video_tag = soup.find("video")
            video_src = video_tag['src'] if video_tag and video_tag.has_attr('src') else None

            # Get video title from <title>
            title_tag = soup.find("title")
            title = title_tag.text.replace(" - MyTube", "") if title_tag else file

            videos_data.append({
                "filename": file,
                "video_src": video_src,
                "video_title": title,
                "taken_down": file in taken_down
            })

    return render_template("admin.html", videos=videos_data)

@app.route("/admin/restore/<filename>", methods=["POST"])
@admin_required
def restore_video(filename):
    path = os.path.join("templates", filename)
    if not os.path.exists(path):
        return "Video not found", 404

    with open("takedowns.json", "r") as f:
        data = json.load(f)

    if filename in data:
        data.remove(filename)

    with open("takedowns.json", "w") as f:
        json.dump(data, f, indent=2)

    return redirect("/admin")

@app.route("/admin/takedown/<filename>", methods=["POST"])
@admin_required
def takedown_video(filename):
    path = os.path.join("templates", filename)
    if not os.path.exists(path):
        return "Video not found", 404

    with open("takedowns.json", "r") as f:
        data = json.load(f)

    if filename not in data:
        data.append(filename)

    with open("takedowns.json", "w") as f:
        json.dump(data, f, indent=2)

    return redirect("/admin")



class User(UserMixin):
    def __init__(self, id_, username, password_hash, role='user'):
        self.id = id_
        self.username = username
        self.password_hash = password_hash
        self.role = role

    @staticmethod
    def get(user_id):
        con = sqlite3.connect("mytube.db")
        cur = con.cursor()
        cur.execute("SELECT id, username, password_hash, role FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        con.close()
        if row:
            return User(*row)
        return None

    @staticmethod
    def get_by_username(username):
        con = sqlite3.connect("mytube.db")
        cur = con.cursor()
        cur.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        con.close()
        if row:
            return User(*row)
        return None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Routes
# Home page
@app.route('/')
def index():
    base_path = app.root_path
    videos_html_path = os.path.join(base_path, 'templates', 'videos.html')
    meta_folder = os.path.join(base_path, 'templates')  # change if needed
    uploads_folder = os.path.join(base_path, 'uploads')

    videos = []
    max_videos = 3

    try:
        with open("takedowns.json", "r") as f:
            taken_down = json.load(f)
    except FileNotFoundError:
        taken_down = []

    if not os.path.exists(videos_html_path):
        print("❌ videos.html not found.")
        return render_template('index.html', top_videos=[])

    with open(videos_html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        links = soup.select('div.videos a[href]')

    for link in links:
        if len(videos) >= max_videos:
            break

        title = link.text.strip()
        meta_href = link.get('href')
        if not meta_href:
            continue

        meta_file = meta_href.split('/')[-1]  # e.g. Mt-XYZ.html
        meta_path = os.path.join(meta_folder, meta_file)

        if not os.path.exists(meta_path):
            print(f"⚠️ Metadata file missing: {meta_path}")
            continue

        with open(meta_path, 'r', encoding='utf-8') as meta_f:
            meta_soup = BeautifulSoup(meta_f.read(), 'html.parser')

            # Grab video filename
            video_tag = meta_soup.find('video')
            video_src = None
            if video_tag:
                # Prefer <source> tag inside <video>
                source_tag = video_tag.find('source')
                if source_tag and source_tag.has_attr('src'):
                    video_src = source_tag['src']
                elif video_tag.has_attr('src'):
                    video_src = video_tag['src']

            if not video_src:
                print(f"⚠️ No <video src> found in {meta_file}")
                continue

            video_filename = os.path.basename(unquote(video_src))
            video_path = os.path.join(uploads_folder, video_filename)
            if not os.path.exists(video_path):
                print(f"⚠️ Video file missing: {video_filename}")
                continue

            uploader = "Unknown"
            description = "No description"
            
            uploader_tag = meta_soup.find('p', class_='uploader')
            if uploader_tag:
                uploader = uploader_tag.text.strip().replace("Uploader: ", "")

            desc_tag = meta_soup.find('p', class_='description')
            if desc_tag:
                description = desc_tag.text.strip()

            videos.append({
                'filename': video_filename,
                'title': title,
                'uploader': uploader,
                'description': description,
                'taken_down': meta_file in taken_down,
                'filename_html': meta_file
            })

    return render_template('index.html', top_videos=videos)
    

@app.route("/channel/<username>/edit", methods=["GET", "POST"])
@login_required
def edit_channel(username):
    if current_user.username != username:
        abort(403)

    # Load current data
    with open("channel_data.json", "r", encoding="utf-8") as f:
        channel_data = json.load(f)

    current_bio = channel_data.get(username, {}).get("bio", "")

    if request.method == "POST":
        new_bio = request.form.get("bio", "").strip()
        if username not in channel_data:
            channel_data[username] = {}
        channel_data[username]["bio"] = new_bio

        with open("channel_data.json", "w", encoding="utf-8") as f:
            json.dump(channel_data, f, indent=2)

        return redirect(url_for("channel_page", username=username))

    return render_template("edit_channel.html", username=username, current_bio=current_bio)


@app.route("/channel/<username>")
def channel_page(username):
    videos = []
    template_dir = os.path.join(app.root_path, 'templates')

    # Load bio & badges
    with open("channel_data.json", "r", encoding="utf-8") as f:
        channel_data = json.load(f)
    bio = channel_data.get(username, {}).get("bio", "")

    # Load takedowns
    try:
        with open("takedowns.json", "r", encoding="utf-8") as f:
            takedowns = json.load(f)
    except:
        takedowns = {}

    for filename in os.listdir(template_dir):
        if filename.startswith("Mt-") and filename.endswith(".html"):
            file_path = os.path.join(template_dir, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
                uploader_tag = soup.find('p', class_='uploader')
                if uploader_tag:
                    text = uploader_tag.text.strip().lower()
                    if text.startswith("uploader:"):
                        actual_uploader = text.replace("uploader:", "").strip()
                        if actual_uploader == username.lower():
                            title_tag = soup.find('title')
                            title = title_tag.text.strip().replace(" - MyTube", "") if title_tag else filename

                            video_tag = soup.find('video')
                            video_src = None
                            if video_tag and video_tag.has_attr('src'):
                                video_src = video_tag['src']
                            elif video_tag:
                                source_tag = video_tag.find('source')
                                if source_tag and source_tag.has_attr('src'):
                                    video_src = source_tag['src']

                            video_filename = os.path.basename(video_src) if video_src else None

                            # ✅ Check takedown
                            is_taken_down = filename in takedowns

                            videos.append({
                                'title': title,
                                'html_filename': filename,
                                'filename': video_filename,
                                'taken_down': is_taken_down
                            })


    return render_template("channel.html", username=username, videos=videos, bio=bio)


@app.route('/delete-video', methods=['POST'])
@login_required
def delete_video():
    html_filename = request.form.get('html_filename')
    if not html_filename:
        return redirect(request.referrer or url_for('index'))

    # Check video exists and belongs to current user
    template_dir = os.path.join(app.root_path, 'templates')
    file_path = os.path.join(template_dir, html_filename)
    if not os.path.exists(file_path):
        return redirect(request.referrer or url_for('index'))

    # Verify ownership by reading uploader from the video HTML
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        uploader_tag = soup.find('p', class_='uploader')
        if not uploader_tag or f"Uploader: {current_user.username}" not in uploader_tag.text:
            return redirect(request.referrer or url_for('index'))

    # Delete the video HTML page
    os.remove(file_path)

    # Also delete the actual video file
    video_tag = soup.find('video')
    video_src = video_tag.get('src') if video_tag and video_tag.has_attr('src') else None
    if not video_src:
        source_tag = video_tag.find('source') if video_tag else None
        if source_tag and source_tag.has_attr('src'):
            video_src = source_tag['src']

    if video_src:
        video_filename = os.path.basename(video_src)
        video_path = os.path.join(app.root_path, 'uploads', video_filename)
        if os.path.exists(video_path):
            os.remove(video_path)

    # Path to videos.html
    videos_html_path = os.path.join(app.root_path, 'templates', 'videos.html')

    # Try to remove the link from videos.html
    try:
        with open(videos_html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        videos_div = soup.find('div', class_='videos')
        if videos_div:
            anchors = videos_div.find_all('a', href=True)
            for anchor in anchors:
                if html_filename in anchor['href']:
                    # Remove the anchor and possibly <br> after it
                    next_sibling = anchor.find_next_sibling()
                    anchor.decompose()
                    if next_sibling and next_sibling.name == 'br':
                        next_sibling.decompose()
                    break

        # Write back the modified HTML
        with open(videos_html_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))

    except Exception as e:
        print(f"❌ Failed to update videos.html: {e}")

    return redirect(url_for('channel_page', username=current_user.username))


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = sanitize(request.form["username"])
        password = request.form["password"]
        hash_pw = generate_password_hash(password)

        try:
            con = sqlite3.connect("mytube.db")
            cur = con.cursor()
            cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hash_pw))
            con.commit()
            con.close()
            return redirect("/login")
        except:
            error = "User already exists!"

    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect("/")
        else:
            error = "Username or password is invalid"
    return render_template("login.html", error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

@app.route("/delete_account", methods=["GET", "POST"])
@login_required
def delete_account():
    if request.method == "POST":
        delete_videos = request.form.get("delete_videos") == "on"
        username = current_user.username

        # Remove from SQL
        con = sqlite3.connect("mytube.db")
        cur = con.cursor()
        cur.execute("DELETE FROM users WHERE id = ?", (current_user.id,))
        con.commit()
        con.close()

        # Remove from JSON
        with open("channel_data.json", "r+", encoding="utf-8") as f:
            data = json.load(f)
            if username in data:
                del data[username]
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2)

        # Delete their videos (HTML + video files + remove from videos.html)
        if delete_videos:
            template_dir = os.path.join(app.root_path, 'templates')
            video_dir = os.path.join(app.root_path, 'uploads')
            videos_html = os.path.join(template_dir, "videos.html")

            # Load takedowns if used
            takedowns = {}
            if os.path.exists("takedowns.json"):
                with open("takedowns.json", "r", encoding="utf-8") as tf:
                    takedowns = json.load(tf)

            new_video_list = ""
            if os.path.exists(videos_html):
                with open(videos_html, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f, 'html.parser')
                    for a in soup.select("div.videos a"):
                        page_name = a.get("href", "").split("/")[-1]
                        page_path = os.path.join(template_dir, page_name)
                        if os.path.exists(page_path):
                            delete_file = False
                            with open(page_path, "r", encoding="utf-8") as pf:
                                content = pf.read()
                                if f"Uploader: {username}" in content:
                                    delete_file = True

                            if delete_file:
                                os.remove(page_path)


                                # Try deleting the video file
                                psoup = BeautifulSoup(content, 'html.parser')
                                vsrc = psoup.find("video")
                                if vsrc:
                                    src = vsrc.get("src")
                                    if src:
                                        fname = os.path.basename(src)
                                        fpath = os.path.join(video_dir, fname)
                                        if os.path.exists(fpath):
                                            os.remove(fpath)
                                # Remove from takedowns
                                if page_name in takedowns:
                                    del takedowns[page_name]

                # Rewrite videos.html
                with open(videos_html, "w", encoding="utf-8") as f:
                    f.write('<div class="videos">\n' + new_video_list + '</div>')

                # Save updated takedowns
                with open("takedowns.json", "w", encoding="utf-8") as tf:
                    json.dump(takedowns, tf, indent=2)

        logout_user()
        return redirect("/")

    return render_template("delete_account.html", username=current_user.username)


#@app.route("/upload-video", methods=["GET", "POST"])
#@login_required
#def upload():
#    if request.method == "POST":
#        title = request.form["videoName"]
#       uploader = current_user.username
#
#       con = sqlite3.connect("mytube.db")
#       cur = con.cursor()
#       con.commit()
#       con.close()
#       return f"Video '{title}' uploaded by {uploader}!"

#   return render_template("upload-video.html", username=current_user.username)

# Route to serve uploaded video files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Upload video route with error handling for duplicate filenames
@app.route('/upload-video', methods=['GET', 'POST'])
@login_required
def upload_video():
    if request.method == 'POST':
        name = current_user.username
        video_name = sanitize(request.form.get("videoName", "").strip())
        description = sanitize(request.form.get("description", "").strip())
        video_file = request.files.get("video")

        if not video_file or not video_name:
            return "Missing video or title", 400

        # 🔀 Generate random filename for the video (to avoid overwrites)
        ext = os.path.splitext(video_file.filename)[1]
        video_filename = ''.join(random.choices(string.ascii_letters + string.digits, k=12)) + ext
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)

        # 💾 Save video file
        video_file.save(video_path)

        # 🧪 Generate random HTML filename for the video page
        random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        html_filename = f"Mt-{random_string}.html"
        video_url = url_for('uploaded_file', filename=video_filename)

        # 🧠 Generate HTML content for the video page
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3163176186394702"
        crossorigin="anonymous"></script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{video_name} - MyTube</title>
    <link rel="icon" type="image/png" href="{{{{ url_for('static', filename='MyTube.png') }}}}">
    <link href="{{{{ url_for('static', filename='style.css') }}}}" rel="stylesheet" type="text/css">
</head>
<body>
    <h1>MyTube</h1>
    <button onclick="location.href='{{{{ url_for('index') }}}}'">Home</button>
    <button onclick="location.href='{{{{ url_for('videos') }}}}'">Videos</button>
    <br>
    {{% if taken_down %}}
        <img src="{{{{ url_for('static', filename='Removed.png') }}}}" alt="Removed" style="max-width: 100%;height: 200px">
    {{% else %}}
        <video src="{video_url}" controls></video>
    {{% endif %}}

    {{% if taken_down %}}
        <h2>This video has been taken down</h2>
    {{% else %}}
        <h2>{video_name}</h2>
    {{% endif %}}
    <p class='uploader'><a href='/channel/{name}'>Uploader: {name}</a></p>
    <p>Description: {description}</p>
</body>
<br><br>

<footer>
  <section>
    <p>© 2023-25 MyTube, this guy Labs, FusionCore Corp. All rights reserved.   [MyTube v{{{{ ver }}}}]</p>
  </section>
</footer>
</html>
"""

        # 💾 Save the HTML page
        new_template_path = os.path.join(TEMPLATE_FOLDER, html_filename)
        with open(new_template_path, 'w', encoding='utf-8') as file:
            file.write(html_content)

        # 🧩 Update videos.html with the new video link
        try:
            with open(VIDEOS_HTML_PATH, 'r', encoding='utf-8') as file:
                videos_html = file.read()

            new_anchor_html = f'<a href="/video/{html_filename}">{video_name}</a><br>\n'
            start_tag = '<div class="videos">'
            videos_html = videos_html.replace(start_tag, f'{start_tag}\n    {new_anchor_html}')

            with open(VIDEOS_HTML_PATH, 'w', encoding='utf-8') as file:
                file.write(videos_html)
        except Exception as e:
            print("❌ Error updating videos.html:", e)

        return redirect(url_for('videos'))

    return render_template("upload-video.html", username=current_user.username)



# Videos page (renders videos.html from the templates folder)
@app.route('/videos')
def videos():
    return render_template('videos.html')

# Route to render a generated video page from the templates folder
@app.route('/video/<filename>')
def video_page(filename):

    template_path = os.path.join("templates", filename)

    # Load takedown list
    with open("takedowns.json", "r") as f:
        taken_down_list = json.load(f)

    # Inject a flag into the template
    return render_template(filename, taken_down=(filename in taken_down_list))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/tos')
def tos():
    return render_template('tos.html')  # Ensure tos.html exists in the templates folder

@app.context_processor
def inject_globals():
    return {
        'ver':'7.4.1',
        'pnver':'7.4.1'
    }


@app.template_filter('nl2br')
def nl2br_filter(s):
    if not s:
        return ''
    
    # Sanitize the text but allow basic formatting
    allowed_tags = ['b', 'u', 'em']
    cleaned = bleach.clean(s, tags=allowed_tags, strip=True)

    # Convert newlines to <br>
    return Markup(cleaned.replace('\n', '<br>'))



if __name__ == '__main__':
    context = ('f87.cer', 'f87.key')
    app.run(ssl_context=context, debug=True, host="0.0.0.0", port=443)
    
