# Mokai | The Youtube Downloader
# Copyright (C) 2026  Ametrine Foundation

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import base64
import os
import random
import re
import signal
import socket
import threading
import time
import uuid
from collections import defaultdict

import flask
import yt_dlp
from flask import Response, jsonify, request, send_from_directory

app = flask.Flask(__name__)
download_progress = {}
download_lock = threading.Lock()
history_file = "history.txt"

home = os.path.expanduser("~")

server_dir = os.path.join(home, ".mokai")


# Change "codecs" to "methods"
@app.route("/shutdown", methods=["POST", "GET"])
def shutdown():
    print("Shutdown signal received from C++. Exiting...")
    os.kill(os.getpid(), signal.SIGINT)
    return "Server shutting down..."


def cleanup_old_downloads():
    """Clean up downloads older than 1 hour"""
    current_time = time.time()
    with download_lock:
        to_remove = []
        for download_id, data in download_progress.items():
            if current_time - data.get("created_at", current_time) > 3600:  # 1 hour
                to_remove.append(download_id)
        for download_id in to_remove:
            del download_progress[download_id]


def update_progress(
    download_id,
    status,
    progress=0,
    message="",
    current_item=0,
    total_items=1,
    item_name="",
):
    """Thread-safe progress update"""
    with download_lock:
        download_progress[download_id] = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_item": current_item,
            "total_items": total_items,
            "item_name": item_name,
            "created_at": download_progress.get(download_id, {}).get(
                "created_at", time.time()
            ),
        }


def download_file(url, file_format, download_id, custom_path=None):
    """Enhanced download function with better progress tracking"""
    try:
        update_progress(download_id, "starting", 0, "Initializing download...")

        # Set download directory
        download_dir = custom_path if custom_path else "./music"

        # Ensure directory exists and is accessible
        try:
            os.makedirs(download_dir, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(download_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except Exception as e:
            raise Exception(
                f"Cannot access download directory '{download_dir}': {str(e)}"
            )

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [lambda d: update_progress_hook(d, download_id)],
            "ignoreerrors": True,
            "extract_flat": False,
            "no_warnings": True,
            "quiet": True,
            "writethumbnail": True,
            "embedthumbnail": True,
            "postprocessors": [
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                }
            ],
        }

        if file_format == "mp3":
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
            ]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            update_progress(
                download_id, "extracting", 5, "Extracting video information..."
            )
            info = ydl.extract_info(url, download=False)

            if "entries" in info:
                # Playlist handling
                entries = [entry for entry in info["entries"] if entry is not None]
                total = len(entries)
                update_progress(
                    download_id,
                    "downloading_multiple",
                    10,
                    f"Found {total} videos in playlist",
                    0,
                    total,
                )

                for count, entry in enumerate(entries, 1):
                    try:
                        item_name = entry.get("title", f"Video {count}")
                        update_progress(
                            download_id,
                            "downloading_multiple",
                            10 + (count - 1) * 80 / total,
                            f"Downloading: {item_name}",
                            count,
                            total,
                            item_name,
                        )

                        ydl.download([entry["webpage_url"]])

                        progress = 10 + count * 80 / total
                        # FIX: Changed typo 'tMokaiotal' to 'total'
                        update_progress(
                            download_id,
                            "downloading_multiple",
                            progress,
                            f"Completed: {item_name}",
                            count,
                            total,
                            item_name,
                        )

                    except Exception as e:
                        print(f"Error downloading {entry.get('title', 'unknown')}: {e}")
                        continue

                update_progress(
                    download_id,
                    "finished",
                    100,
                    f"Successfully downloaded {total} videos!",
                )
            else:
                # Single video handling
                item_name = info.get("title", "Video")
                update_progress(
                    download_id,
                    "downloading",
                    10,
                    f"Downloading: {item_name}",
                    1,
                    1,
                    item_name,
                )

                ydl.download([url])
                update_progress(download_id, "finished", 100, "Download completed!")

    except Exception as e:
        error_msg = str(e)
        if "Video unavailable" in error_msg:
            error_msg = "Video is unavailable or private"
        elif "network" in error_msg.lower():
            error_msg = "Network error. Please check your connection."
        update_progress(download_id, "error", 0, error_msg)


def update_progress_hook(d, download_id):
    """Progress hook for yt-dlp downloads"""
    if d["status"] == "downloading":
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
        percent = (downloaded / total * 100) if total > 0 else 0

        # Get current progress data to maintain item info
        current_data = download_progress.get(download_id, {})
        current_item = current_data.get("current_item", 1)
        total_items = current_data.get("total_items", 1)
        item_name = current_data.get("item_name", "Video")

        if total_items > 1:
            # For playlists, adjust progress within the current item's range
            base_progress = 10 + (current_item - 1) * 80 / total_items
            item_progress = percent * 0.8 / total_items
            final_progress = base_progress + item_progress
            update_progress(
                download_id,
                "downloading_multiple",
                final_progress,
                f"Downloading: {item_name} ({percent:.1f}%)",
                current_item,
                total_items,
                item_name,
            )
        else:
            # Single video
            final_progress = 10 + percent * 0.9
            update_progress(
                download_id,
                "downloading",
                final_progress,
                f"Downloading: {item_name} ({percent:.1f}%)",
                1,
                1,
                item_name,
            )


@app.route("/")
def index():
    cleanup_old_downloads()

    # Read index.html content
    with open(f"{server_dir}/index.html", "r") as f:
        html_content = f.read()

    # Read style.css content and prepare for embedding
    with open(f"{server_dir}/style.css", "r") as f:
        css_content = f.read()
    embedded_css_tag = f"<style>{css_content}</style>"

    embedded_favicon_link = '<link rel="icon" href="/Mokai.png" />'
    try:
        with open(f"{server_dir}/Mokai.png", "rb") as f:
            png_data = f.read()
        base64_png = base64.b64encode(png_data).decode("utf-8")
        embedded_favicon_link = f'<link rel="icon" href="data:image/png;base64,{base64_png}" type="image/png">'
    except FileNotFoundError:
        pass
    html_content = re.sub(
        r'<link\s+rel="icon"[^>]*href="/Mokai\.png"[^>]*\/?>',
        "",
        html_content,
        flags=re.IGNORECASE,
    )
    html_content = re.sub(
        r'<link\s+rel="stylesheet"[^>]*href="style\.css"[^>]*\/?>',
        "",
        html_content,
        flags=re.IGNORECASE,
    )

    if "</head>" in html_content:
        html_content = html_content.replace(
            "<head>", f"<head>{embedded_css_tag}{embedded_favicon_link}", 1
        )
    elif "<body>" in html_content:
        html_content = html_content.replace(
            "<body>", f"<body>{embedded_css_tag}{embedded_favicon_link}", 1
        )
    else:
        html_content = f"{embedded_css_tag}{embedded_favicon_link}{html_content}"

    return Response(html_content, mimetype="text/html")


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url", "").strip()
    format_ = data.get("format", "mp4")
    download_id = data.get("download_id")
    custom_path = data.get("custom_path", "")

    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    if not download_id:
        download_id = str(uuid.uuid4())

    if custom_path:
        if not os.path.isabs(custom_path) and not custom_path.startswith("./"):
            custom_path = "./" + custom_path

        try:
            normalized_path = os.path.normpath(custom_path)
            if ".." in normalized_path.split(os.sep):
                return jsonify(
                    {
                        "status": "error",
                        "message": "Invalid path: directory traversal not allowed",
                    }
                ), 400
        except Exception:
            return jsonify({"status": "error", "message": "Invalid path format"}), 400

    update_progress(download_id, "starting", 0, "Starting download...")

    thread = threading.Thread(
        target=download_file, args=(url, format_, download_id, custom_path)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "download_id": download_id})


@app.route("/progress")
def progress():
    download_id = request.args.get("download_id")
    if not download_id:
        return jsonify({"status": "error", "message": "No download ID provided"}), 400

    with download_lock:
        progress_data = download_progress.get(
            download_id,
            {"status": "unknown", "progress": 0, "message": "Download not found"},
        )

    return jsonify(progress_data)


@app.route("/log", methods=["POST"])
def log():
    data = flask.request.json
    print("JS Console:", data.get("message"))
    return "", 204


if __name__ == "__main__":
    target_port = 2070
    app.run(host="0.0.0.0", port=target_port, debug=False)
