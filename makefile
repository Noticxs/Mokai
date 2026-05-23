# Compiler settings
CXX      = clang++
CXXFLAGS = -std=c++17 -pthread -Wall -O2

# Directories
VENDOR_DIR = vendor
OBJ_DIR    = obj
TARGET     = mokai

LICENSE := LICENSE
DESKTOP := Mokai.desktop
ICON    := icon.png

PREFIX     := /usr/local
BINDIR     := $(PREFIX)/bin
DESKTOPDIR := /usr/share/applications
MOKAIDIR   := /usr/share/Mokai
ICONDIR    := /usr/share/Mokai
DOCDIR     := /usr/share/Mokai
ifeq ($(SUDO_USER),)
MOKDIR := $(HOME)/.mokai
else
USER_HOME := $(shell getent passwd $(SUDO_USER) | cut -d: -f6)
MOKDIR := $(USER_HOME)/.mokai
endif

SRCS = main.cc
OBJS = $(OBJ_DIR)/main.o

PY_CFLAGS = $(shell python3-config --cflags)
PY_LIBS   = $(shell python3-config --embed --libs)

PKG_LIBS = webkit2gtk-4.1 gtk+-3.0

SYS_INCS = $(shell pkg-config --cflags $(PKG_LIBS))
LIBS     = $(shell pkg-config --libs $(PKG_LIBS)) -ldl

WEBVIEW_INC = $(VENDOR_DIR)/webview/core/include/webview

.PHONY: all build init-deps download-dependencies install uninstall clean

all: init-deps download-dependencies build

install:
	install -d $(DESTDIR)$(DOCDIR)
	install -d $(DESTDIR)$(BINDIR)
	install -d $(DESTDIR)$(ICONDIR)
	install -d $(DESTDIR)$(DESKTOPDIR)
	if [ -z "$(SUDO_USER)" ]; then \
		install -d "$(DESTDIR)$(MOKDIR)"; \
	else \
		install -d -o "$(SUDO_USER)" -g "$$(id -gn "$(SUDO_USER)")" "$(DESTDIR)$(MOKDIR)"; \
	fi

	install -m644 $(LICENSE) $(DESTDIR)$(DOCDIR)/LICENSE
	install -m755 $(TARGET)  $(DESTDIR)$(BINDIR)/$(TARGET)
	install -m644 $(ICON)    $(DESTDIR)$(ICONDIR)/icon.png
	install -m644 $(DESKTOP) $(DESTDIR)$(DESKTOPDIR)/$(DESKTOP)

	if [ -z "$(SUDO_USER)" ]; then \
		install -m755 server/app.py "$(DESTDIR)$(MOKDIR)/app.py"; \
	else \
		install -o "$(SUDO_USER)" -g "$$(id -gn "$(SUDO_USER)")" -m755 server/app.py "$(DESTDIR)$(MOKDIR)/app.py"; \
	fi
	if [ -z "$(SUDO_USER)" ]; then \
		install -m755 server/index.html "$(DESTDIR)$(MOKDIR)/index.html"; \
	else \
		install -o "$(SUDO_USER)" -g "$$(id -gn "$(SUDO_USER)")" -m755 server/index.html "$(DESTDIR)$(MOKDIR)/index.html"; \
	fi
	if [ -z "$(SUDO_USER)" ]; then \
		install -m644 server/style.css "$(DESTDIR)$(MOKDIR)/style.css"; \
	else \
		install -o "$(SUDO_USER)" -g "$$(id -gn "$(SUDO_USER)")" -m644 server/style.css "$(DESTDIR)$(MOKDIR)/style.css"; \
	fi
	if [ -z "$(SUDO_USER)" ]; then \
		install -m644 server/Mokai.png "$(DESTDIR)$(MOKDIR)/Mokai.png"; \
	else \
		install -o "$(SUDO_USER)" -g "$$(id -gn "$(SUDO_USER)")" -m644 server/Mokai.png "$(DESTDIR)$(MOKDIR)/Mokai.png"; \
	fi

uninstall:
	rm -f  $(DESTDIR)$(DOCDIR)/LICENSE
	rm -f  $(DESTDIR)$(BINDIR)/$(TARGET)
	rm -f  $(DESTDIR)$(DESKTOPDIR)/$(DESKTOP)
	rm -f  $(DESTDIR)$(ICONDIR)/icon.png
	rmdir  $(DESTDIR)$(MOKAIDIR) 2>/dev/null || true
	rm -rf $(DESTDIR)$(MOKDIR)

init-deps:
	@echo "Installing WebKit and GTK development libraries via pacman..."
	sudo pacman -S --needed --noconfirm webkit2gtk-4.1 gtk3 pkg-config

	@echo "Installing Python dependencies..."
	pip install -r requirements.txt --break-system-packages

	@echo "Installing ffmpeg..."
	sudo pacman -S --needed --noconfirm ffmpeg

download-dependencies:
	@mkdir -p $(VENDOR_DIR)
	@if [ ! -d $(VENDOR_DIR)/webview ]; then \
		echo "Cloning webview repository..."; \
		git clone --depth 1 https://github.com/webview/webview.git $(VENDOR_DIR)/webview; \
	fi

# Link binary
build: $(OBJS)
	$(CXX) $(OBJS) -o $(TARGET) $(LIBS) $(PY_LIBS)
	@echo "Linked binary: $(TARGET)"


# Compile main source file
$(OBJ_DIR)/main.o: main.cc $(WEBVIEW_INC)/webview.h
	@mkdir -p $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -I$(WEBVIEW_INC) $(SYS_INCS) -c main.cc -o $@

clean:
	rm -rf $(OBJ_DIR) $(TARGET)

clean-vendor: clean
	rm -rf $(VENDOR_DIR)
