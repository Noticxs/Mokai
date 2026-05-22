# Mokai

Mokai is a Youtube Downloader built with python and c++.
It is built of YT-DLP library in python.

Mokai uses both Python and C++. Python handles the downloading, and C++ creates the app window using the `webview` library.

The Python part (`app.py`) is a Flask app that manages all download operations. It uses the `yt-dlp` library to get YouTube videos as MP4 or MP3. 

It tracks download progress, even for playlists. This part also serves the app's web interface (HTML, CSS, images) and runs locally on port 2070.

The C++ part (`main.cc`) starts the application. It launches the Python part (`app.py`) in the background. 

Once Python is ready, C++ opens a `webview` window that displays the web interface from the Python app. 

This makes the web-based Python interface look like a regular desktop app. C++ also ensures the Python part stops running when you close the app.

The `makefile` handles building and installing Mokai. It has commands for Arch (`make all-arch`) and Debian-based (`make all-deb`) systems to install necessary software like WebKitGTK, GTK3, `ffmpeg`, and Python packages. 

Finally, `make install` places the app, its files (in `~/.mokai`), documentation, icon, and desktop entry where they belong.

The `Mokai.desktop` file helps Mokai work well with Linux desktops. It gives Mokai an icon and description, making it easy to find and open from your application menu.

```bash
# Clone the repository
git clone https://github.com/Noticxs/Mokai.git

# Build Mokai
cd Mokai
make all-arch # or use make 'all-deb' for Debian-based systems

# Install Mokai
sudo make install
```
