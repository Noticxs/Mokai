import flask
from flask import request, Response, jsonify
import yt_dlp
import os
import threading
import uuid
import time
from collections import defaultdict

app = flask.Flask(__name__)
download_progress = {}
download_lock = threading.Lock()

def cleanup_old_downloads():
    """Clean up downloads older than 1 hour"""
    current_time = time.time()
    with download_lock:
        to_remove = []
        for download_id, data in download_progress.items():
            if current_time - data.get('created_at', current_time) > 3600:  # 1 hour
                to_remove.append(download_id)
        for download_id in to_remove:
            del download_progress[download_id]

def update_progress(download_id, status, progress=0, message='', current_item=0, total_items=1, item_name=''):
    """Thread-safe progress update"""
    with download_lock:
        download_progress[download_id] = {
            'status': status,
            'progress': progress,
            'message': message,
            'current_item': current_item,
            'total_items': total_items,
            'item_name': item_name,
            'created_at': download_progress.get(download_id, {}).get('created_at', time.time())
        }

def download_file(url, file_format, download_id, custom_path=None):
    """Enhanced download function with better progress tracking"""
    try:
        update_progress(download_id, 'starting', 0, 'Initializing download...')
        
        # Set download directory
        download_dir = custom_path if custom_path else './music'
        
        # Ensure directory exists and is accessible
        try:
            os.makedirs(download_dir, exist_ok=True)
            # Test write permissions
            test_file = os.path.join(download_dir, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            raise Exception(f"Cannot access download directory '{download_dir}': {str(e)}")
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [lambda d: update_progress_hook(d, download_id)],
            'ignoreerrors': True,
            'extract_flat': False,
            'no_warnings': True,
            'quiet': True,
            'writethumbnail': True,
            'embedthumbnail': True,
            'postprocessors': [{
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }],
        }

        if file_format == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                },
                {
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False,
                }
            ]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            update_progress(download_id, 'extracting', 5, 'Extracting video information...')
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                # Playlist handling
                entries = [entry for entry in info['entries'] if entry is not None]
                total = len(entries)
                update_progress(download_id, 'downloading_multiple', 10, 
                              f'Found {total} videos in playlist', 0, total)
                
                for count, entry in enumerate(entries, 1):
                    try:
                        item_name = entry.get('title', f'Video {count}')
                        update_progress(download_id, 'downloading_multiple', 
                                      10 + (count-1) * 80 / total, 
                                      f'Downloading: {item_name}', 
                                      count, total, item_name)
                        
                        ydl.download([entry['webpage_url']])
                        
                        progress = 10 + count * 80 / total
                        update_progress(download_id, 'downloading_multiple', progress, 
                                      f'Completed: {item_name}', count, total, item_name)
                        
                    except Exception as e:
                        print(f"Error downloading {entry.get('title', 'unknown')}: {e}")
                        continue
                
                update_progress(download_id, 'finished', 100, 
                              f'Successfully downloaded {total} videos!')
            else:
                # Single video handling
                item_name = info.get('title', 'Video')
                update_progress(download_id, 'downloading', 10, 
                              f'Downloading: {item_name}', 1, 1, item_name)
                ydl.download([url])
                update_progress(download_id, 'finished', 100, 'Download completed!')
                
    except Exception as e:
        error_msg = str(e)
        if 'Video unavailable' in error_msg:
            error_msg = 'Video is unavailable or private'
        elif 'network' in error_msg.lower():
            error_msg = 'Network error. Please check your connection.'
        update_progress(download_id, 'error', 0, error_msg)

def update_progress_hook(d, download_id):
    """Progress hook for yt-dlp downloads"""
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
        percent = (downloaded / total * 100) if total > 0 else 0
        
        # Get current progress data to maintain item info
        current_data = download_progress.get(download_id, {})
        current_item = current_data.get('current_item', 1)
        total_items = current_data.get('total_items', 1)
        item_name = current_data.get('item_name', 'Video')
        
        if total_items > 1:
            # For playlists, adjust progress within the current item's range
            base_progress = 10 + (current_item - 1) * 80 / total_items
            item_progress = percent * 0.8 / total_items
            final_progress = base_progress + item_progress
            update_progress(download_id, 'downloading_multiple', final_progress,
                          f'Downloading: {item_name} ({percent:.1f}%)',
                          current_item, total_items, item_name)
        else:
            # Single video
            final_progress = 10 + percent * 0.9
            update_progress(download_id, 'downloading', final_progress,
                          f'Downloading: {item_name} ({percent:.1f}%)',
                          1, 1, item_name)

@app.route('/')
def index():
    cleanup_old_downloads()  # Clean up old downloads on page load
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Downloader</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 500px;
            transition: transform 0.3s ease;
        }
        
        .container:hover {
            transform: translateY(-5px);
        }
        
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 2.5em;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
            font-size: 1.1em;
        }
        
        input[type="text"], select {
            width: 100%;
            padding: 15px;
            border: 2px solid #e1e5e9;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s ease;
            background: #fff;
        }
        
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            transform: translateY(-1px);
        }
        
        .download-btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
        }
        
        .download-btn:active {
            transform: translateY(0);
        }
        
        #popup {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(5px);
            align-items: center;
            justify-content: center;
            z-index: 1000;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        #popup-content {
            background: white;
            padding: 40px;
            border-radius: 20px;
            text-align: center;
            max-width: 400px;
            width: 90%;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.2);
            animation: slideUp 0.3s ease;
        }
        
        @keyframes slideUp {
            from { transform: translateY(30px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        .loader {
            width: 60px;
            height: 60px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        #progress-text {
            font-size: 1.1em;
            margin-bottom: 20px;
            color: #333;
            font-weight: 500;
        }
        
        .progress-container {
            margin-bottom: 20px;
        }
        
        #progress-bar {
            width: 100%;
            height: 12px;
            border-radius: 10px;
            appearance: none;
            background: #f0f0f0;
        }
        
        #progress-bar::-webkit-progress-bar {
            background: #f0f0f0;
            border-radius: 10px;
        }
        
        #progress-bar::-webkit-progress-value {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 10px;
            transition: width 0.3s ease;
        }
        
        #progress-bar::-moz-progress-bar {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 10px;
        }
        
        .progress-details {
            font-size: 0.9em;
            color: #666;
            margin-top: 10px;
        }
        
        .error {
            color: #e74c3c;
        }
        
        .success {
            color: #27ae60;
        }
        
        .path-hint {
            font-size: 0.85em;
            color: #888;
            margin-top: 5px;
            font-style: italic;
        }
            .container {
                padding: 20px;
                margin: 10px;
            }
            
            h1 {
                font-size: 2em;
            }
            
            #popup-content {
                padding: 30px 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Video Downloader</h1>
        <form id="download-form">
            <div class="form-group">
                <label for="url">📎 Video URL:</label>
                <input type="text" id="url" name="url" placeholder="Paste YouTube/video URL here..." required>
            </div>
            <div class="form-group">
                <label for="format">🎵 Format:</label>
                <select id="format" name="format">
                    <option value="mp4">🎥 MP4 (Video)</option>
                    <option value="mp3">🎵 MP3 (Audio Only)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="custom-path">📁 Download Directory (Optional):</label>
                <input type="text" id="custom-path" name="custom-path" placeholder="Leave empty for default (./music)">
                <div class="path-hint">Examples: /Users/username/Downloads, C:\\Downloads, ./my_videos</div>
            </div>
            <button type="submit" class="download-btn">⬇️ Download</button>
        </form>
    </div>

    <div id="popup">
        <div id="popup-content">
            <div class="loader"></div>
            <p id="progress-text">Starting download...</p>
            <div class="progress-container">
                <progress id="progress-bar" value="0" max="100"></progress>
            </div>
            <div id="progress-details" class="progress-details"></div>
        </div>
    </div>

    <script>
        document.getElementById('download-form').onsubmit = function(e) {
            e.preventDefault();
            
            const url = document.getElementById('url').value.trim();
            const format = document.getElementById('format').value;
            const customPath = document.getElementById('custom-path').value.trim();
            const downloadId = Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
            
            // Show popup
            document.getElementById('popup').style.display = 'flex';
            document.getElementById('progress-text').textContent = 'Starting download...';
            document.getElementById('progress-bar').value = 0;
            document.getElementById('progress-details').textContent = '';
            
            // Start download
            fetch('/download', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    url: url, 
                    format: format, 
                    download_id: downloadId,
                    custom_path: customPath || null
                })
            }).catch(err => {
                console.error('Download request failed:', err);
                document.getElementById('progress-text').textContent = 'Failed to start download';
                document.getElementById('progress-text').className = 'error';
                setTimeout(() => document.getElementById('popup').style.display = 'none', 3000);
            });

            let finished = false;
            const interval = setInterval(() => {
                fetch('/progress?download_id=' + downloadId)
                .then(r => r.json())
                .then(data => {
                    const progressBar = document.getElementById('progress-bar');
                    const progressText = document.getElementById('progress-text');
                    const progressDetails = document.getElementById('progress-details');
                    
                    progressBar.value = data.progress || 0;
                    
                    if (data.status === 'starting') {
                        progressText.textContent = 'Initializing...';
                        progressText.className = '';
                    } else if (data.status === 'extracting') {
                        progressText.textContent = 'Extracting video information...';
                        progressText.className = '';
                    } else if (data.status === 'downloading') {
                        progressText.textContent = data.message || 'Downloading...';
                        progressText.className = '';
                        progressDetails.textContent = `Progress: ${Math.round(data.progress)}%`;
                    } else if (data.status === 'downloading_multiple') {
                        progressText.textContent = data.message || 'Downloading playlist...';
                        progressText.className = '';
                        if (data.total_items > 1) {
                            progressDetails.textContent = `Item ${data.current_item} of ${data.total_items} • ${Math.round(data.progress)}%`;
                        } else {
                            progressDetails.textContent = `Progress: ${Math.round(data.progress)}%`;
                        }
                    } else if (data.status === 'finished') {
                        progressText.textContent = data.message || 'Download completed! ✅';
                        progressText.className = 'success';
                        progressDetails.textContent = '100% Complete';
                        if (!finished) {
                            finished = true;
                            setTimeout(() => {
                                document.getElementById('popup').style.display = 'none';
                                document.getElementById('url').value = '';
                            }, 3000);
                            clearInterval(interval);
                        }
                    } else if (data.status === 'error') {
                        progressText.textContent = 'Error: ' + (data.message || 'Unknown error occurred');
                        progressText.className = 'error';
                        progressDetails.textContent = '';
                        setTimeout(() => document.getElementById('popup').style.display = 'none', 4000);
                        clearInterval(interval);
                    }
                })
                .catch(err => {
                    console.error('Progress check failed:', err);
                    if (!finished) {
                        document.getElementById('progress-text').textContent = 'Connection error';
                        document.getElementById('progress-text').className = 'error';
                        setTimeout(() => document.getElementById('popup').style.display = 'none', 3000);
                        clearInterval(interval);
                    }
                });
            }, 500); // Check more frequently for smoother updates
        };
    </script>
</body>
</html>
"""
    return Response(html, mimetype='text/html')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url', '').strip()
    format_ = data.get('format', 'mp4')
    download_id = data.get('download_id')
    custom_path = data.get('custom_path', '').strip()
    
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400
    
    if not download_id:
        download_id = str(uuid.uuid4())
    
    # Validate custom path if provided
    if custom_path:
        # Basic path validation
        if not os.path.isabs(custom_path) and not custom_path.startswith('./'):
            custom_path = './' + custom_path
        
        # Security check - prevent directory traversal attacks
        try:
            normalized_path = os.path.normpath(custom_path)
            if '..' in normalized_path.split(os.sep):
                return jsonify({'status': 'error', 'message': 'Invalid path: directory traversal not allowed'}), 400
        except Exception:
            return jsonify({'status': 'error', 'message': 'Invalid path format'}), 400
    
    # Initialize progress tracking
    update_progress(download_id, 'starting', 0, 'Starting download...')
    
    # Start download in background thread
    thread = threading.Thread(target=download_file, args=(url, format_, download_id, custom_path))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'started', 'download_id': download_id})

@app.route('/progress')
def progress():
    download_id = request.args.get('download_id')
    if not download_id:
        return jsonify({'status': 'error', 'message': 'No download ID provided'}), 400
    
    with download_lock:
        progress_data = download_progress.get(download_id, {
            'status': 'unknown', 
            'progress': 0, 
            'message': 'Download not found'
        })
    
    return jsonify(progress_data)

@app.route('/log', methods=['POST'])
def log():
    data = flask.request.json
    print('JS Console:', data.get('message'))
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=2070, debug=False)
