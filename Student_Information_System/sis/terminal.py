"""Large, centered, responsive retro-terminal UI with six color themes."""

import os
import shutil
import sys
import textwrap
from datetime import datetime

from .password_input import read_masked


def rgb(red, green, blue, bold=False):
    return f"\033[{'1;' if bold else ''}38;2;{red};{green};{blue}m"


PALETTES = {
    "Matrix Green": {
        "primary": rgb(94, 230, 136), "accent": rgb(157, 255, 182, True),
        "muted": rgb(83, 151, 109), "warn": rgb(255, 123, 119),
        "good": rgb(106, 249, 151), "soft": rgb(180, 214, 192),
        "description": "Classic hacker green / forest glow",
    },
    "Amber Vintage": {
        "primary": rgb(255, 191, 75), "accent": rgb(255, 219, 126, True),
        "muted": rgb(162, 128, 75), "warn": rgb(255, 105, 100),
        "good": rgb(236, 214, 145), "soft": rgb(225, 205, 169),
        "description": "Warm amber / 1980s computer terminal",
    },
    "Ocean Blue": {
        "primary": rgb(102, 214, 247), "accent": rgb(151, 232, 255, True),
        "muted": rgb(83, 150, 176), "warn": rgb(255, 139, 126),
        "good": rgb(122, 238, 193), "soft": rgb(188, 219, 233),
        "description": "Cool cyan / digital command deck",
    },
    "Midnight Gold": {
        "primary": rgb(218, 171, 70), "accent": rgb(255, 217, 111, True),
        "muted": rgb(133, 117, 92), "warn": rgb(255, 114, 102),
        "good": rgb(184, 218, 159), "soft": rgb(231, 218, 190),
        "description": "Luxury black-and-gold control room",
    },
    "Royal Purple": {
        "primary": rgb(198, 151, 255), "accent": rgb(233, 200, 255, True),
        "muted": rgb(131, 109, 169), "warn": rgb(255, 134, 154),
        "good": rgb(136, 235, 222), "soft": rgb(218, 205, 238),
        "description": "Violet neon / futuristic console",
    },
    "Crimson Classic": {
        "primary": rgb(255, 117, 117), "accent": rgb(255, 179, 171, True),
        "muted": rgb(156, 98, 105), "warn": rgb(255, 221, 107),
        "good": rgb(149, 233, 176), "soft": rgb(231, 206, 207),
        "description": "Deep red / vintage mission control",
    },
}


def enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except (AttributeError, OSError):
        pass


class Terminal:
    def __init__(self, theme="Matrix Green"):
        enable_windows_ansi()
        self.theme = theme if theme in PALETTES else "Matrix Green"
        self.color_enabled = ("NO_COLOR" not in os.environ and
                              (sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"))

    def color(self, value, category="primary"):
        return (f"{PALETTES[self.theme][category]}{value}\033[0m"
                if self.color_enabled else str(value))

    def width(self):
        """Increase content area up to 132 columns, but fit small windows."""
        columns = shutil.get_terminal_size(fallback=(120, 38)).columns
        return min(132, max(20, columns - 4))

    def margin(self):
        columns = shutil.get_terminal_size(fallback=(120, 38)).columns
        return max(0, (columns - self.width()) // 2)

    def line(self, value="", extra_indent=0):
        """Write one or more lines, all with the same centered outer margin."""
        prefix = " " * (self.margin() + extra_indent)
        for part in str(value).split("\n"):
            print(prefix + part)

    def rule(self, character="-"):
        self.line(self.color(character * self.width(), "muted"))

    def frame_line(self, content="", tone="soft", centered=False):
        """A full-width framed line (spaces also centered in the terminal)."""
        inside = self.width() - 4
        value = str(content).replace("\n", " ").replace("\r", " ")[:inside]
        value = value.center(inside) if centered else value.ljust(inside)
        self.line(self.color("|", "muted") + " " + self.color(value, tone) +
                  " " + self.color("|", "muted"))

    def banner(self):
        self.line(self.color("+" + "=" * (self.width() - 2) + "+", "accent"))
        self.frame_line(centered=True, tone="muted")
        if self.width() >= 72:
            for row in (
                "  ____    ___    ____  ",
                " / ___|  |_ _|  / ___| ",
                " \\___ \\   | |   \\___ \\ ",
                "  ___) |  | |    ___) |",
                " |____/  |___|  |____/ ",
            ):
                self.frame_line(row, "accent", centered=True)
        else:
            self.frame_line("[ S I S ]", "accent", centered=True)
        self.frame_line("S T U D E N T   I N F O R M A T I O N   S Y S T E M", "accent", centered=True)
        self.frame_line("NORSU  /  ACADEMIC RECORDS CONSOLE  /  v4.0", "primary", centered=True)
        self.frame_line("SECURE LOGIN  +  LIVE .TXT DATABASE  +  6 TERMINAL THEMES", "soft", centered=True)
        self.frame_line(centered=True, tone="muted")
        self.line(self.color("+" + "=" * (self.width() - 2) + "+", "accent"))

    def screen(self, title="MAIN DASHBOARD"):
        if sys.stdout.isatty() and os.environ.get("SIS_NO_CLEAR") != "1":
            print("\033[2J\033[H", end="")
        rows = shutil.get_terminal_size(fallback=(120, 38)).lines
        if rows >= 38:
            print("\n" * min(3, max(1, (rows - 36) // 4)), end="")
        self.banner()
        self.line(self.color("  >>  " + title.upper(), "accent"))
        stamp = datetime.now().strftime("%d %b %Y  |  %I:%M %p")
        self.line(self.color(f"  {stamp}   //   THEME: {self.theme}", "muted"))
        self.rule()

    def heading(self, text):
        self.line()
        self.line(self.color("  [ " + str(text).upper() + " ]", "accent"))
        self.rule("-")

    def text(self, message=""):
        for part in str(message).splitlines() or [""]:
            self.line(part)

    def info(self, message):
        self.line("  " + self.color("[INFO]", "primary") + " " + str(message))

    def success(self, message):
        self.line("  " + self.color("[ OK ]", "good") + " " + str(message))

    def error(self, message):
        self.line("  " + self.color("[WARN]", "warn") + " " + str(message))

    def login_panel(self, setup=False):
        """A smaller card centered *inside* the main centered layout."""
        width = min(76, self.width())
        indent = (self.width() - width) // 2
        border = "+" + "-" * (width - 2) + "+"
        label = "FIRST-TIME ADMINISTRATOR SETUP" if setup else "AUTHORIZED PERSONNEL ONLY"
        self.line()
        self.line(self.color(border, "accent"), indent)
        self.line(self.color("|", "muted") + self.color(label.center(width - 2), "accent") +
                  self.color("|", "muted"), indent)
        self.line(self.color("|", "muted") + " " +
                  "Passwords display as * while you type.".center(width - 4) + " " +
                  self.color("|", "muted"), indent)
        self.line(self.color(border, "accent"), indent)
        self.line()

    def _metric_panel(self, title, value, detail, size):
        inner = size - 4
        heading = "-- " + title.upper() + " "
        top = "+" + heading + "-" * max(0, size - 2 - len(heading)) + "+"
        return (top,
                "| " + str(value).rjust(inner) + " |",
                "| " + str(detail)[:inner].ljust(inner) + " |",
                "+" + "-" * (size - 2) + "+")

    def dashboard_cards(self, user, metrics):
        self.heading("Active session / system overview")
        identity = (f"USER: {user['username']}    ACCESS: {user['role']}    STATUS: AUTHORIZED")
        self.frame_line(identity.center(self.width() - 4), "good")
        left_size = (self.width() - 3) // 2
        right_size = self.width() - 3 - left_size
        stats = [
            ("01 / Students", f"{metrics['students']:03d}", f"{metrics['active']} active profiles"),
            ("02 / Subjects", f"{metrics['subjects']:03d}", "catalog courses"),
            ("03 / Enrollments", f"{metrics['enrollments']:03d}", "saved registrations"),
            ("04 / Graded", f"{metrics['graded']:03d}",
             f"{metrics['passing']} passed / {metrics['failing']} failed"),
        ]
        self.line()
        for pair in (stats[:2], stats[2:]):
            first = self._metric_panel(*pair[0], left_size)
            second = self._metric_panel(*pair[1], right_size)
            for i, (a, b) in enumerate(zip(first, second)):
                tone = "accent" if i in (0, 1) else "muted" if i == 3 else "soft"
                self.line(self.color(a, tone) + "   " + self.color(b, tone))
        graded = metrics["graded"]
        if graded:
            bar_width = min(36, max(8, self.width() - 42))
            filled = round(bar_width * metrics["passing"] / graded)
            bar = "#" * filled + "." * (bar_width - filled)
            self.line("\n  " + self.color("PASS RATE", "muted") + "  " +
                      self.color("[" + bar + "]", "primary") +
                      f"  {100 * metrics['passing'] / graded:.1f}%")
        else:
            self.info("No recorded grades yet. Use Grades to add results.")

    def menu(self, title, options, back="Back"):
        self.heading(title)
        use_grid = len(options) >= 5 and self.width() >= 86
        if use_grid:
            cell_width = (self.width() - 7) // 2
            for index in range(0, len(options), 2):
                display = []
                for key, label in options[index:index + 2]:
                    label = str(label)[:cell_width - 5].ljust(cell_width - 5)
                    display.append(self.color(f"[{key}]", "accent") + self.color("  " + label, "soft"))
                self.line("  " + "   ".join(display))
        else:
            for key, label in options:
                self.line("  " + self.color(f"[{key}]", "accent") + "  " + str(label))
        self.line()
        self.line("  " + self.color("[0]", "muted") + "  " + str(back))
        self.rule()
        valid = {key.upper() for key, _ in options} | {"0"}
        while True:
            choice = self.ask("Select option").upper()
            if choice in valid:
                return choice
            self.error("Invalid option. Choose one of the numbers shown.")

    def theme_menu(self):
        self.heading("Theme showroom / live color swatches")
        options = []
        for index, (name, properties) in enumerate(PALETTES.items(), 1):
            marker = "  * ACTIVE" if self.theme == name else ""
            sample = f"[{index}]  " + name.ljust(18) + "| " + properties["description"] + marker
            if self.color_enabled:
                self.line(properties["accent"] + "  " + sample + "\033[0m")
            else:
                self.line("  " + sample)
            options.append(str(index))
        self.line()
        self.line("  " + self.color("[0]", "muted") + "  Back to Settings")
        self.rule()
        while True:
            choice = self.ask("Select a theme")
            if choice in options + ["0"]:
                return choice
            self.error("Choose one of the six theme numbers.")

    def _prompt(self, prompt):
        return " " * (self.margin() + 3) + self.color("> " + str(prompt) + ": ", "primary")

    def ask(self, prompt, default=None):
        suffix = f" [{default}]" if default is not None else ""
        answer = input(self._prompt(f"{prompt}{suffix}")).strip()
        return answer if answer else (str(default) if default is not None else "")

    def ask_secret(self, prompt="Password"):
        return read_masked(self._prompt(prompt))

    def yes_no(self, prompt, default=False):
        marker = "Y/n" if default else "y/N"
        while True:
            value = self.ask(f"{prompt} ({marker})").lower()
            if not value:
                return default
            if value in ("y", "yes"):
                return True
            if value in ("n", "no"):
                return False
            self.error("Enter Y or N.")

    def pause(self):
        input(" " * (self.margin() + 3) + self.color("[ENTER] Return to menu...", "muted"))

    def table(self, headings, rows, widths=None):
        if widths is None:
            widths = [max(len(str(head)), 10) for head in headings]
        widths = list(widths)
        room = self.width() - 3 * len(widths) - 1
        while sum(widths) > room:
            choices = [i for i, w in enumerate(widths) if w > 5]
            if not choices:
                break
            widths[max(choices, key=lambda i: widths[i])] -= 1

        def clip(value, width):
            val = str(value).replace("\n", " ").replace("\r", " ")
            return (val if len(val) <= width else val[:max(0, width - 3)] + "...").ljust(width)

        boundary = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        extra = max(0, (self.width() - len(boundary)) // 2)
        self.heading("Stored records / live file data")
        self.line(self.color(boundary, "muted"), extra)
        self.line(self.color("| " + " | ".join(clip(h, w) for h, w in zip(headings, widths)) + " |", "accent"), extra)
        self.line(self.color(boundary, "muted"), extra)
        for row in rows:
            cells = []
            for value, width in zip(row, widths):
                category = ("good" if str(value).lower() in ("passed", "active")
                            else "warn" if str(value).lower() in ("failed", "inactive", "disabled")
                            else None)
                cell = clip(value, width)
                cells.append(self.color(cell, category) if category else cell)
            self.line("| " + " | ".join(cells) + " |", extra)
        if not rows:
            self.line("| " + "No records found.".center(len(boundary) - 4) + " |", extra)
        self.line(self.color(boundary, "muted"), extra)
        self.line(self.color(f"  {len(rows)} record(s) shown", "muted"), extra)

    def paragraph(self, body):
        for item in str(body).splitlines():
            if not item:
                self.line()
            else:
                for line in textwrap.wrap(item, width=max(20, self.width() - 6),
                                          break_long_words=False, replace_whitespace=False):
                    self.line("  " + line)
