"""File panel widgets for dual-pane file browser - MC v1.0."""

import os
import string
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, ListView, ListItem, Label
from textual.reactive import reactive
from textual.message import Message

if TYPE_CHECKING:
    from src.ui.themes import ColorScheme


# Special path constant for "This PC" view
THIS_PC = "This PC"


def get_available_drives() -> list[tuple[str, str, int, int]]:
    """Get list of available drives on Windows.

    Returns list of tuples: (drive_letter, label, total_bytes, free_bytes)
    """
    drives = []

    if os.name == 'nt':
        # Windows: use ctypes to get drive info
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drive_path = f"{letter}:\\"
                    try:
                        # Get drive type
                        drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
                        # 2=Removable, 3=Fixed, 4=Network, 5=CD-ROM, 6=RAM disk
                        if drive_type in (2, 3, 4, 5, 6):
                            # Get volume info
                            label_buf = ctypes.create_unicode_buffer(256)
                            ctypes.windll.kernel32.GetVolumeInformationW(
                                drive_path, label_buf, 256, None, None, None, None, 0
                            )
                            label = label_buf.value or "Local Disk"

                            # Get disk space
                            free_bytes = ctypes.c_ulonglong(0)
                            total_bytes = ctypes.c_ulonglong(0)
                            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                                drive_path,
                                ctypes.byref(free_bytes),
                                ctypes.byref(total_bytes),
                                None
                            )
                            drives.append((letter, label, total_bytes.value, free_bytes.value))
                    except Exception:
                        # Drive exists but can't get info (e.g., empty CD drive)
                        drives.append((letter, "Drive", 0, 0))
                bitmask >>= 1
        except Exception:
            # Fallback: just check for common drives
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    drives.append((letter, "Drive", 0, 0))
    else:
        # Unix-like: show mount points
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mount_point = parts[1]
                        if mount_point.startswith('/media') or mount_point.startswith('/mnt') or mount_point == '/':
                            try:
                                stat = os.statvfs(mount_point)
                                total = stat.f_blocks * stat.f_frsize
                                free = stat.f_bfree * stat.f_frsize
                                label = os.path.basename(mount_point) or "Root"
                                drives.append((mount_point, label, total, free))
                            except Exception:
                                drives.append((mount_point, os.path.basename(mount_point) or "Root", 0, 0))
        except Exception:
            # Fallback for non-Linux Unix
            drives.append(("/", "Root", 0, 0))

    return drives


class DriveListItem(ListItem):
    """A list item representing a drive."""

    def __init__(self, drive_letter: str, label: str, total_bytes: int, free_bytes: int,
                 color_scheme: Optional["ColorScheme"] = None, **kwargs):
        super().__init__(**kwargs)
        self.drive_letter = drive_letter
        self.drive_label = label
        self.total_bytes = total_bytes
        self.free_bytes = free_bytes
        self._color_scheme = color_scheme
        # For Windows, construct path like "C:\"; for Unix, use mount point directly
        if os.name == 'nt':
            self.drive_path = Path(f"{drive_letter}:\\")
        else:
            self.drive_path = Path(drive_letter)

    def compose(self) -> ComposeResult:
        """Compose the drive list item."""
        if os.name == 'nt':
            display_name = f"{self.drive_label} ({self.drive_letter}:)"
        else:
            display_name = f"{self.drive_label} ({self.drive_letter})"

        if self.total_bytes > 0:
            total_str = self._format_size(self.total_bytes)
            free_str = self._format_size(self.free_bytes)
            size_info = f"{free_str} free / {total_str}"
        else:
            size_info = ""

        label = f"  {display_name:<36} {size_info:>20}"
        yield Label(label, classes="drive", id="item-label")

    def on_mount(self) -> None:
        """Apply colors when mounted."""
        self._apply_colors()

    def _apply_colors(self) -> None:
        """Apply colors based on color scheme."""
        if not self._color_scheme:
            return

        scheme = self._color_scheme
        try:
            label_widget = self.query_one("#item-label", Label)
            label_widget.styles.color = scheme.directory_fg
            label_widget.styles.text_style = "bold"
        except Exception:
            pass

    def _format_size(self, size: int) -> str:
        """Format size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:3.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"


class FileListItem(ListItem):
    """A file list item with file information - no icons, just colors."""

    is_selected: reactive[bool] = reactive(False)

    def __init__(self, path: Path, filename: str, is_dir: bool, size: int,
                 mtime: float = 0, color_scheme: Optional["ColorScheme"] = None, **kwargs):
        super().__init__(**kwargs)
        self.file_path = path
        self.filename = filename
        self.is_dir = is_dir
        self.file_size = size
        self.mtime = mtime
        self._color_scheme = color_scheme

    def _get_file_type(self) -> str:
        """Get the file type for color styling."""
        if self.is_dir:
            return "directory"
        elif self.filename.lower().endswith((".exe", ".bat", ".cmd", ".ps1", ".com")):
            return "executable"
        elif self.filename.lower().endswith((".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".arc", ".arj", ".lzh")):
            return "archive"
        else:
            return "file"

    def _format_date(self) -> str:
        """Format modification time as date string."""
        if self.mtime > 0:
            dt = datetime.fromtimestamp(self.mtime)
            return dt.strftime("%Y-%m-%d %H:%M")
        return ""

    def compose(self) -> ComposeResult:
        """Compose the file list item - Norton Commander style (no icons)."""
        if self.is_dir:
            size_str = "<DIR>"
        else:
            size_str = self._format_size(self.file_size)

        date_str = self._format_date()

        # Add selection marker
        # Format: marker + name (30 chars) + size (10 chars) + date (16 chars)
        marker = ">" if self.is_selected else " "
        label = f"{marker} {self.filename:<30} {size_str:>10}  {date_str:>16}"
        file_type = self._get_file_type()
        yield Label(label, classes=file_type, id="item-label")

    def on_mount(self) -> None:
        """Apply colors when item is mounted."""
        self._apply_colors()

    def _apply_colors(self) -> None:
        """Apply colors based on file type and color scheme."""
        if not self._color_scheme:
            return

        scheme = self._color_scheme
        file_type = self._get_file_type()

        try:
            label_widget = self.query_one("#item-label", Label)

            # Apply color based on file type
            if file_type == "directory":
                label_widget.styles.color = scheme.directory_fg
                label_widget.styles.text_style = "bold"
            elif file_type == "executable":
                label_widget.styles.color = scheme.executable_fg
            elif file_type == "archive":
                label_widget.styles.color = scheme.archive_fg
            else:
                label_widget.styles.color = scheme.panel_fg
        except Exception:
            pass

    def watch_is_selected(self, new_value: bool) -> None:
        """React to selection changes."""
        if self.is_mounted:
            # Update the label text
            label_widget = self.query_one("#item-label", Label)
            if self.is_dir:
                size_str = "<DIR>"
            else:
                size_str = self._format_size(self.file_size)

            date_str = self._format_date()
            marker = ">" if new_value else " "
            label_widget.update(f"{marker} {self.filename:<30} {size_str:>10}  {date_str:>16}")

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:3.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"


class FilePanel(Container):
    """A file panel showing directory contents."""

    current_path: reactive[str] = reactive(os.getcwd)

    class PathChanged(Message):
        """Message sent when path changes."""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    class FileSelected(Message):
        """Message sent when a file is selected."""

        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    def __init__(self, initial_path: Optional[str] = None, show_hidden: bool = False,
                 sort_order: str = "name_asc", **kwargs):
        super().__init__(**kwargs)
        self._initial_path = initial_path or os.getcwd()
        self.selected_files = set()
        self.show_hidden = show_hidden
        self.sort_order = sort_order
        self._color_scheme: Optional["ColorScheme"] = None

    def set_color_scheme(self, scheme: "ColorScheme") -> None:
        """Set the color scheme for this panel and refresh items."""
        self._color_scheme = scheme
        if self.is_mounted:
            self._apply_panel_colors()
            # Always refresh the list to rebuild items with new colors
            self.refresh_file_list()

    def _apply_panel_colors(self) -> None:
        """Apply color scheme to panel elements."""
        if not self._color_scheme:
            return

        scheme = self._color_scheme

        # Apply to panel container
        self.styles.background = scheme.panel_bg
        self.styles.color = scheme.panel_fg
        self.styles.border = ("solid", scheme.panel_border)

        # Apply to panel header
        try:
            header = self.query_one(".file-panel--header")
            header.styles.background = scheme.header_bg
            header.styles.color = scheme.header_fg
        except Exception:
            pass

        # Apply to list view and set highlight colors
        try:
            list_view = self.query_one("#file-list", ListView)
            list_view.styles.background = scheme.panel_bg
            list_view.styles.color = scheme.panel_fg
            list_view.styles.scrollbar_background = scheme.panel_bg
            list_view.styles.scrollbar_color = scheme.panel_border
            # Set scrollbar colors for better visibility
            list_view.styles.scrollbar_color_hover = scheme.cursor_bg
            list_view.styles.scrollbar_color_active = scheme.cursor_bg
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        """Compose the file panel."""
        with Vertical():
            yield Static(self._initial_path, classes="file-panel--header", id="path-header")
            yield ListView(id="file-list")

    def on_mount(self) -> None:
        """Handle mount event."""
        self.current_path = self._initial_path
        self._apply_panel_colors()
        self.refresh_file_list()

    def on_focus(self) -> None:
        """Handle focus event."""
        pass  # Will be caught by parent

    def watch_current_path(self, new_path: str) -> None:
        """Handle path changes."""
        if not self.is_mounted:
            return
        self.refresh_file_list()
        self.update_header()
        self.post_message(self.PathChanged(new_path))

    def count_files_in_selection(self) -> tuple[int, int]:
        """Count total files and directories in selection (including subdirectories)."""
        total_files = 0
        total_dirs = 0

        for path_str in self.selected_files:
            path = Path(path_str)
            if path.is_dir():
                total_dirs += 1
                # Count files in this directory recursively
                try:
                    for item in path.rglob("*"):
                        if item.is_file():
                            total_files += 1
                        elif item.is_dir():
                            total_dirs += 1
                except (PermissionError, OSError):
                    pass  # Skip directories we can't access
            else:
                total_files += 1

        return total_files, total_dirs

    def update_header(self) -> None:
        """Update the panel header with path and selection info."""
        if not self.is_mounted:
            return
        header = self.query_one("#path-header", Static)
        sel_count = len(self.selected_files)
        if sel_count > 0:
            files, dirs = self.count_files_in_selection()
            if dirs > 0:
                header.update(f"{self.current_path} [{sel_count} items: {files} files, {dirs} dirs]")
            else:
                header.update(f"{self.current_path} [{files} files selected]")
        else:
            header.update(self.current_path)

    def refresh_file_list(self) -> None:
        """Refresh the file list with proper colors."""
        file_list = self.query_one("#file-list", ListView)
        file_list.clear()

        # Handle "This PC" view - show available drives
        if self.current_path == THIS_PC:
            self._show_drives_list(file_list)
            return

        try:
            path = Path(self.current_path)

            # Add parent directory entry or "This PC" for root drives
            if path.parent != path:
                item = FileListItem(path.parent, "..", True, 0, mtime=0, color_scheme=self._color_scheme)
                file_list.append(item)
            else:
                # At root of a drive - add ".." to go to "This PC"
                item = FileListItem(Path(THIS_PC), "..", True, 0, mtime=0, color_scheme=self._color_scheme)
                file_list.append(item)

            # Get all entries
            entries = []
            try:
                for entry in path.iterdir():
                    # Filter hidden files if show_hidden is False
                    if not self.show_hidden and entry.name.startswith('.'):
                        continue
                    # On Windows, also check for hidden attribute
                    if not self.show_hidden and os.name == 'nt':
                        try:
                            import stat as stat_module
                            if entry.stat().st_file_attributes & stat_module.FILE_ATTRIBUTE_HIDDEN:
                                continue
                        except (AttributeError, OSError):
                            pass

                    try:
                        stat = entry.stat()
                        entries.append((entry.name, entry.is_dir(), stat.st_size, stat.st_mtime, entry))
                    except (PermissionError, OSError):
                        # Skip files we can't access
                        entries.append((entry.name, entry.is_dir(), 0, 0, entry))
            except PermissionError:
                pass

            # Sort entries based on sort_order
            entries = self._sort_entries(entries)

            # Add items to list - pass color scheme to each item
            for name, is_dir, size, mtime, entry_path in entries:
                item = FileListItem(entry_path, name, is_dir, size, mtime=mtime, color_scheme=self._color_scheme)
                file_list.append(item)

        except Exception as e:
            file_list.append(ListItem(Label(f"Error: {str(e)}")))

        # Set focus to first item
        if file_list.children:
            file_list.index = 0

    def _show_drives_list(self, file_list: ListView) -> None:
        """Show the list of available drives."""
        drives = get_available_drives()
        for drive_letter, label, total_bytes, free_bytes in drives:
            item = DriveListItem(drive_letter, label, total_bytes, free_bytes,
                               color_scheme=self._color_scheme)
            file_list.append(item)
        # Set focus to first item
        if file_list.children:
            file_list.index = 0

    def _sort_entries(self, entries: list) -> list:
        """Sort entries based on current sort_order.

        Each entry is (name, is_dir, size, mtime, path).
        Directories always come first.
        """
        sort_key = self.sort_order.rsplit("_", 1)[0]  # e.g., "name", "size", "date", "ext"
        reverse = self.sort_order.endswith("_desc")

        if sort_key == "name":
            # Sort by name (case-insensitive)
            entries.sort(key=lambda x: (not x[1], x[0].lower()), reverse=False)
            if reverse:
                # Reverse only within dirs and files separately
                dirs = [e for e in entries if e[1]]
                files = [e for e in entries if not e[1]]
                dirs.sort(key=lambda x: x[0].lower(), reverse=True)
                files.sort(key=lambda x: x[0].lower(), reverse=True)
                entries = dirs + files
        elif sort_key == "size":
            # Sort by size
            entries.sort(key=lambda x: (not x[1], x[2] if not reverse else -x[2]))
        elif sort_key == "date":
            # Sort by modification date (mtime is now at index 3)
            entries.sort(key=lambda x: (not x[1], x[3] if not reverse else -x[3]))
        elif sort_key == "ext":
            # Sort by extension
            def get_ext(name):
                if '.' in name:
                    return name.rsplit('.', 1)[-1].lower()
                return ""
            entries.sort(key=lambda x: (not x[1], get_ext(x[0])), reverse=False)
            if reverse:
                dirs = [e for e in entries if e[1]]
                files = [e for e in entries if not e[1]]
                dirs.sort(key=lambda x: get_ext(x[0]), reverse=True)
                files.sort(key=lambda x: get_ext(x[0]), reverse=True)
                entries = dirs + files
        else:
            # Default: dirs first, then by name
            entries.sort(key=lambda x: (not x[1], x[0].lower()))

        return entries

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection."""
        if isinstance(event.item, DriveListItem):
            # Navigate into the selected drive
            self.current_path = str(event.item.drive_path)
        elif isinstance(event.item, FileListItem):
            if event.item.is_dir:
                # Check if this is the ".." item pointing to "This PC"
                if event.item.filename == ".." and str(event.item.file_path) == THIS_PC:
                    self.current_path = THIS_PC
                else:
                    self.current_path = str(event.item.file_path)
            else:
                self.post_message(self.FileSelected(event.item.file_path))

    def navigate_up(self) -> None:
        """Navigate to parent directory."""
        if self.current_path == THIS_PC:
            return  # Already at top level
        path = Path(self.current_path)
        if path.parent != path:
            self.current_path = str(path.parent)
        else:
            # At root of drive, go to "This PC"
            self.current_path = THIS_PC

    def navigate_to(self, path: str) -> None:
        """Navigate to specific path."""
        if path == THIS_PC:
            self.current_path = THIS_PC
        elif os.path.isdir(path):
            self.current_path = path

    def go_to_this_pc(self) -> None:
        """Navigate to This PC view showing all drives."""
        self.current_path = THIS_PC

    def get_focused_item(self) -> Optional[FileListItem]:
        """Get the currently focused item."""
        file_list = self.query_one("#file-list", ListView)
        if file_list.index is not None and file_list.index < len(file_list.children):
            item = list(file_list.children)[file_list.index]
            if isinstance(item, FileListItem):
                return item
        return None

    def toggle_selection(self) -> None:
        """Toggle selection of the currently focused item."""
        item = self.get_focused_item()
        if item and item.filename != "..":
            item_path = str(item.file_path)
            if item_path in self.selected_files:
                self.selected_files.remove(item_path)
                item.is_selected = False
                item.remove_class("-selected")
            else:
                self.selected_files.add(item_path)
                item.is_selected = True
                item.add_class("-selected")

            # Update selection counter in header
            self.update_header()

            # Move to next item
            file_list = self.query_one("#file-list", ListView)
            if file_list.index is not None and file_list.index < len(file_list.children) - 1:
                file_list.index += 1

    def clear_selection(self) -> None:
        """Clear all selections."""
        file_list = self.query_one("#file-list", ListView)
        for child in file_list.children:
            if isinstance(child, FileListItem):
                child.is_selected = False
                child.remove_class("-selected")
        self.selected_files.clear()
        self.update_header()

    def get_selected_items(self) -> list[Path]:
        """Get list of selected file paths."""
        return [Path(p) for p in self.selected_files]

    def on_key(self, event) -> None:
        """Handle key presses."""
        if event.key == "space":
            self.toggle_selection()
            event.prevent_default()
            event.stop()
