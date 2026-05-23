// Mokai | The Youtube Downloader
// Copyright (C) 2026  Ametrine Foundation

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#define WEBVIEW_IMPLEMENTATION
#define PY_SSIZE_T_CLEAN
#include "webview.h"
#include <python3.14/Python.h>
#include <iostream>
#include <thread>
#include <stddef.h>
#include <filesystem>

#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

namespace fs = std::filesystem;

const char* SERVER_FILE = ".mokai/app.py";

bool is_server_ready(const char* ip, int port) {
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return false;

    sockaddr_in serv_addr;
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(port);
    inet_pton(AF_INET, ip, &serv_addr.sin_addr);

    bool ready = (connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    close(sock);
    return ready;
}

int main(int argc, char *argv[]) {
    const char* home_env = std::getenv("HOME");
    if (!home_env) {
        std::cerr << "Error: HOME environment variable is not set." << std::endl;
        return 1;
    }

    Py_Initialize();

    // Properly chain the paths using std::filesystem::path
    fs::path serverPath = fs::path(home_env) / SERVER_FILE;

    // Store the string representation explicitly so the underlying char buffer remains valid
    std::string script_str = serverPath.string();
    const char* script = script_str.c_str();
    const char* url = "http://127.0.0.1:2070";

    PyThreadState* main_thread_state = PyEval_SaveThread();

    // Capture by value (or copy script_str) so the background thread references valid memory
    std::thread python_thread([script_str]() {
        PyGILState_STATE gstate = PyGILState_Ensure();

        const char* script_ptr = script_str.c_str();
        FILE* fp = fopen(script_ptr, "r");
        if (fp != nullptr) {
            int result = PyRun_SimpleFileEx(fp, script_ptr, 1);
            if (result != 0) {
                std::cerr << "Failed to execute Python code cleanly." << std::endl;
            }
        } else {
            std::cerr << "Could not open file: " << script_ptr << std::endl;
        }

        // Release the lock state
        PyGILState_Release(gstate);
    });

    std::cout << "Waiting for backend server to wake up on port 2070..." << std::endl;
    int retries = 0;
    while (!is_server_ready("127.0.0.1", 2070)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        retries++;
        if (retries > 120) {
            std::cerr << "Error: Python backend server failed to bind in time." << std::endl;
            break;
        }
    }

    webview::webview w(true, nullptr);
    w.set_title("Mokai");
    w.set_size(1092, 1080, WEBVIEW_HINT_NONE);
    w.navigate(url);
    w.run();

    std::cout << "UI closed. Terminating background runtime..." << std::endl;

    python_thread.detach();

    PyEval_RestoreThread(main_thread_state);
    Py_Finalize();

    return 0;
}
