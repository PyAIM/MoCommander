"""Main application for Mo Commander (MC) v1.0 - A modern dual-pane file manager."""

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from enum import Enum

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static, Input, Button, Label, OptionList, ListView
from textual.widgets.option_list import Option
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.command import Provider, Hit

from src.ui.panels import FilePanel
from src.ui.themes import ThemeManager
from src.core.config import Config
from src.core.file_ops import FileOperations


class ActionType(Enum):
    """Types of undoable actions."""
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"
    MKDIR = "mkdir"
    RENAME = "rename"


@dataclass
class UndoAction:
    """Represents an undoable action."""
    action_type: ActionType
    source: Path
    destination: Optional[Path] = None
    backup_path: Optional[Path] = None  # For deleted files


class UndoManager:
    """Manages undo history for file operations."""

    def __init__(self, max_history: int = 50):
        self.history: list[UndoAction] = []
        self.max_history = max_history
        self.backup_dir = Path(tempfile.gettempdir()) / "mocommander_undo"
        self.backup_dir.mkdir(exist_ok=True)

    def record_copy(self, source: Path, destination: Path) -> None:
        """Record a copy operation."""
        self._add_action(UndoAction(ActionType.COPY, source, destination))

    def record_move(self, source: Path, destination: Path) -> None:
        """Record a move operation."""
        self._add_action(UndoAction(ActionType.MOVE, source, destination))

    def record_delete(self, path: Path) -> bool:
        """Record a delete operation by backing up the file first."""
        try:
            backup_name = f"{len(self.history)}_{path.name}"
            backup_path = self.backup_dir / backup_name
            if path.is_dir():
                shutil.copytree(path, backup_path)
            else:
                shutil.copy2(path, backup_path)
            self._add_action(UndoAction(ActionType.DELETE, path, backup_path=backup_path))
            return True
        except Exception:
            return False

    def record_mkdir(self, path: Path) -> None:
        """Record a mkdir operation."""
        self._add_action(UndoAction(ActionType.MKDIR, path))

    def record_rename(self, old_path: Path, new_path: Path) -> None:
        """Record a rename operation."""
        self._add_action(UndoAction(ActionType.RENAME, old_path, new_path))

    def _add_action(self, action: UndoAction) -> None:
        """Add an action to history."""
        self.history.append(action)
        if len(self.history) > self.max_history:
            # Remove oldest and clean up any associated backup
            oldest = self.history.pop(0)
            if oldest.backup_path and oldest.backup_path.exists():
                if oldest.backup_path.is_dir():
                    shutil.rmtree(oldest.backup_path)
                else:
                    oldest.backup_path.unlink()

    def can_undo(self) -> bool:
        """Check if there's an action to undo."""
        return len(self.history) > 0

    def undo(self) -> tuple[bool, str]:
        """Undo the last action. Returns (success, message)."""
        if not self.history:
            return False, "Nothing to undo"

        action = self.history.pop()

        try:
            if action.action_type == ActionType.COPY:
                # Undo copy by deleting the copied file
                if action.destination.exists():
                    if action.destination.is_dir():
                        shutil.rmtree(action.destination)
                    else:
                        action.destination.unlink()
                return True, f"Undid copy: removed {action.destination.name}"

            elif action.action_type == ActionType.MOVE:
                # Undo move by moving back
                if action.destination.exists():
                    shutil.move(str(action.destination), str(action.source))
                    return True, f"Undid move: restored {action.source.name}"
                return False, f"Cannot undo: {action.destination.name} no longer exists"

            elif action.action_type == ActionType.DELETE:
                # Undo delete by restoring from backup
                if action.backup_path and action.backup_path.exists():
                    if action.backup_path.is_dir():
                        shutil.copytree(action.backup_path, action.source)
                        shutil.rmtree(action.backup_path)
                    else:
                        shutil.copy2(action.backup_path, action.source)
                        action.backup_path.unlink()
                    return True, f"Undid delete: restored {action.source.name}"
                return False, "Cannot undo: backup not found"

            elif action.action_type == ActionType.MKDIR:
                # Undo mkdir by removing the directory (only if empty)
                if action.source.exists() and action.source.is_dir():
                    try:
                        action.source.rmdir()  # Only removes if empty
                        return True, f"Undid mkdir: removed {action.source.name}"
                    except OSError:
                        return False, f"Cannot undo: {action.source.name} is not empty"
                return False, f"Cannot undo: {action.source.name} no longer exists"

            elif action.action_type == ActionType.RENAME:
                # Undo rename by renaming back
                if action.destination.exists():
                    action.destination.rename(action.source)
                    return True, f"Undid rename: restored {action.source.name}"
                return False, f"Cannot undo: {action.destination.name} no longer exists"

        except Exception as e:
            return False, f"Undo failed: {e}"

        return False, "Unknown action type"

    def get_last_action_description(self) -> str:
        """Get a description of the last undoable action."""
        if not self.history:
            return "Nothing to undo"
        action = self.history[-1]
        if action.action_type == ActionType.COPY:
            return f"Undo copy of {action.destination.name}"
        elif action.action_type == ActionType.MOVE:
            return f"Undo move of {action.source.name}"
        elif action.action_type == ActionType.DELETE:
            return f"Undo delete of {action.source.name}"
        elif action.action_type == ActionType.MKDIR:
            return f"Undo mkdir {action.source.name}"
        elif action.action_type == ActionType.RENAME:
            return f"Undo rename of {action.source.name}"
        return "Unknown action"

    def cleanup(self) -> None:
        """Clean up all backup files."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)


class ThemeCommands(Provider):
    """Command provider for theme selection."""

    async def search(self, query: str):
        """Search for matching themes."""
        matcher = self.matcher(query)
        app = self.app

        if isinstance(app, MoCommander):
            for theme_name in app.theme_manager.get_available_themes():
                command_text = f"Switch to {theme_name} theme"
                score = matcher.match(command_text)
                # Yield all results when query is empty, or matching results otherwise
                if not query or score > 0:
                    yield Hit(
                        score if query else 1.0,
                        matcher.highlight(command_text),
                        lambda t=theme_name: app.switch_to_theme(t),
                        help=f"Change color scheme to {theme_name}"
                    )


class FileViewerScreen(ModalScreen[None]):
    """Modal screen for viewing file contents."""

    DEFAULT_CSS = """
    FileViewerScreen {
        align: center middle;
    }

    #viewer-container {
        width: 90%;
        height: 90%;
        border: thick $background 80%;
        background: $surface;
        padding: 0;
    }

    #viewer-title {
        dock: top;
        width: 100%;
        height: 3;
        padding: 1;
        text-style: bold;
        background: $primary;
        color: $text;
    }

    #viewer-content {
        width: 100%;
        height: 1fr;
        padding: 1;
        overflow-y: scroll;
        background: $surface;
    }

    #viewer-footer {
        dock: bottom;
        width: 100%;
        height: 3;
        padding: 1;
        background: $primary;
        color: $text;
        content-align: center middle;
    }
    """

    def __init__(self, file_path: Path):
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        from textual.widgets import TextArea

        with Vertical(id="viewer-container"):
            yield Label(f"File: {self.file_path.name}", id="viewer-title")

            # Try to read the file
            try:
                content = self.file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    content = self.file_path.read_text(encoding='latin-1')
                except Exception as e:
                    content = f"Error reading file: {e}\n\n(This may be a binary file)"
            except Exception as e:
                content = f"Error reading file: {e}"

            viewer = TextArea(content, id="viewer-content", read_only=True)
            yield viewer
            yield Label("Press ESC or F3 to close", id="viewer-footer")

    def on_key(self, event) -> None:
        if event.key == "escape" or event.key == "f3":
            self.dismiss()


class InputDialog(ModalScreen[str]):
    """Modal dialog for text input."""

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }

    #dialog {
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
    }

    #dialog-input {
        width: 100%;
        margin: 1 0;
    }

    #dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        layout: horizontal;
    }

    #dialog-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, prompt: str, default: str = ""):
        super().__init__()
        self.dialog_title = title
        self.dialog_prompt = prompt
        self.default_value = default

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.dialog_title, id="dialog-title")
            yield Label(self.dialog_prompt)
            yield Input(value=self.default_value, id="dialog-input")
            with Horizontal(id="dialog-buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            value = self.query_one(Input).value
            self.dismiss(value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ConfirmDialog(ModalScreen[str]):
    """Modal dialog for confirmations with Yes/No/Yes to All options."""

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    #confirm-dialog {
        width: 60;
        height: 13;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #confirm-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $warning;
    }

    #confirm-message {
        width: 100%;
        margin: 1 0;
    }

    #confirm-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        layout: horizontal;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, message: str, show_all: bool = False):
        super().__init__()
        self.dialog_title = title
        self.dialog_message = message
        self.show_all = show_all

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self.dialog_title, id="confirm-title")
            yield Label(self.dialog_message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes (Y)", variant="error", id="yes")
                yield Button("No (N)", variant="primary", id="no")
                if self.show_all:
                    yield Button("Yes to All (A)", variant="warning", id="all")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss("yes")
        elif event.key == "n" or event.key == "escape":
            self.dismiss("no")
        elif event.key == "a" and self.show_all:
            self.dismiss("all")


class SortDialog(ModalScreen[str]):
    """Modal dialog for sorting options."""

    DEFAULT_CSS = """
    SortDialog {
        align: center middle;
    }

    #sort-dialog {
        width: 50;
        height: 18;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #sort-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        margin-bottom: 1;
    }

    #sort-options {
        width: 100%;
        height: 10;
        margin: 0;
    }

    #sort-footer {
        width: 100%;
        height: 2;
        content-align: center middle;
        margin-top: 1;
    }
    """

    SORT_OPTIONS = [
        ("name_asc", "Name (A-Z)"),
        ("name_desc", "Name (Z-A)"),
        ("size_asc", "Size (Smallest first)"),
        ("size_desc", "Size (Largest first)"),
        ("date_asc", "Date (Oldest first)"),
        ("date_desc", "Date (Newest first)"),
        ("ext_asc", "Extension (A-Z)"),
        ("ext_desc", "Extension (Z-A)"),
    ]

    def __init__(self, current_sort: str = "name_asc"):
        super().__init__()
        self.current_sort = current_sort

    def compose(self) -> ComposeResult:
        with Vertical(id="sort-dialog"):
            yield Label("Sort Files By", id="sort-title")
            option_list = OptionList(id="sort-options")
            for key, label in self.SORT_OPTIONS:
                marker = "> " if key == self.current_sort else "  "
                option_list.add_option(Option(f"{marker}{label}", id=key))
            yield option_list
            yield Label("Enter to select, ESC to cancel", id="sort-footer")

    def on_mount(self) -> None:
        option_list = self.query_one("#sort-options", OptionList)
        option_list.focus()
        # Find and highlight current sort option
        for i, (key, _) in enumerate(self.SORT_OPTIONS):
            if key == self.current_sort:
                option_list.highlighted = i
                break

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class MoCommander(App):
    """Mo Commander v1.0 - A modern dual-pane file manager."""

    # Base CSS for layout only - colors applied dynamically via CSS variables
    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 1fr;
        layout: horizontal;
    }

    FilePanel {
        width: 1fr;
        height: 1fr;
        margin: 0 1;
    }

    .file-panel--header {
        dock: top;
        height: 1;
        padding: 0 1;
        text-style: bold;
    }

    #file-list {
        height: 1fr;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    /* Ensure list items span full width */
    #file-list > ListItem {
        width: 1fr;
        height: 1;
    }

    /* Labels inside list items - full width */
    #file-list > ListItem Label {
        width: 1fr;
    }

    #footer-container {
        dock: bottom;
        height: 1;
        layout: horizontal;
    }

    #copyright-text {
        width: auto;
        dock: right;
        padding: 0 1;
        background: #000000;
        color: #00ffff;
    }

    .directory {
        text-style: bold;
    }

    /* Selected items (space bar) */
    ListView > ListItem.-selected {
        text-style: bold;
    }

    /* Header styling for better contrast */
    Header {
        background: #000000;
        color: #ffffff;
    }

    HeaderTitle {
        background: #000000;
        color: #00ffff;
        text-style: bold;
    }

    HeaderClock {
        background: #000000;
        color: #ffffff;
    }

    /* Footer styling for better contrast */
    Footer {
        background: #000000;
    }

    FooterKey {
        background: #000000;
        color: #ffffff;
    }

    Footer > .footer--highlight {
        background: #00ffff;
        color: #000000;
    }

    Footer > .footer--key {
        background: #000000;
        color: #00ffff;
        text-style: bold;
    }

    Footer > .footer--description {
        background: #000000;
        color: #ffffff;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("f1", "help", "Help", show=True),
        Binding("f2", "toggle_theme", "Theme", show=True),
        Binding("f3", "view", "View", show=True),
        Binding("f4", "edit", "Edit", show=True),
        Binding("f5", "copy", "Copy", show=True),
        Binding("f6", "move", "Move", show=True),
        Binding("f7", "mkdir", "MkDir", show=True),
        Binding("f8", "delete", "Delete", show=True),
        Binding("f9", "command_palette", "Menu", show=True),
        Binding("f10", "quit", "Quit", show=True),
        Binding("tab", "switch_panel", "Switch", show=False),
        Binding("ctrl+r", "refresh", "Refresh", show=False),
        Binding("ctrl+h", "toggle_hidden", "Hidden", show=False),
        Binding("ctrl+z", "undo", "Undo", show=False),
        Binding("ctrl+n", "rename", "Rename", show=False),
        Binding("ctrl+s", "sort", "Sort", show=False),
        Binding("ctrl+d", "goto_drives", "Drives", show=False),
        Binding("ctrl+backslash", "command_palette", show=False),
    ]

    COMMANDS = {ThemeCommands}

    active_panel: reactive[str] = reactive("left")

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.theme_manager = ThemeManager(self.config.get_theme())
        self.file_ops = FileOperations()
        self.undo_manager = UndoManager()
        self.left_panel = None
        self.right_panel = None
        self.show_hidden = self.config.get("show_hidden", False)
        self.current_sort = self.config.get("sort_order", "name_asc")

        # Register our custom Textual themes
        for name, theme in self.theme_manager.get_all_textual_themes().items():
            self.register_theme(theme)

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            self.left_panel = FilePanel(
                initial_path=self.config.get_left_panel_path(),
                show_hidden=self.show_hidden,
                sort_order=self.current_sort,
                id="left-panel"
            )
            self.right_panel = FilePanel(
                initial_path=self.config.get_right_panel_path(),
                show_hidden=self.show_hidden,
                sort_order=self.current_sort,
                id="right-panel"
            )
            yield self.left_panel
            yield self.right_panel
        with Horizontal(id="footer-container"):
            yield Footer()
            yield Static("(c) 2025 - Mo Commander", id="copyright-text")

    def on_mount(self) -> None:
        """Handle mount event."""
        self.title = "Mo Commander"
        self.sub_title = "MC v1.0"
        # Apply theme after a short delay to ensure widgets are ready
        self.call_after_refresh(self._initial_theme_apply)
        self.update_panel_focus()

    def _initial_theme_apply(self) -> None:
        """Apply theme on initial load."""
        self.apply_theme()

    def on_unmount(self) -> None:
        """Clean up on exit."""
        self.undo_manager.cleanup()

    def apply_theme(self) -> None:
        """Apply the current theme to all UI elements."""
        scheme = self.theme_manager.get_scheme()

        if not self.is_mounted:
            return

        # Set the Textual theme - this handles highlight colors via CSS variables
        textual_theme_name = self.theme_manager.get_textual_theme_name()
        self.theme = textual_theme_name

        # Apply additional styling that Textual's theme doesn't cover
        self.screen.styles.background = scheme.panel_bg

        # Apply to header
        try:
            header = self.query_one(Header)
            header.styles.background = scheme.header_bg
            header.styles.color = scheme.header_fg
        except Exception:
            pass

        # Apply to copyright text
        try:
            copyright_text = self.query_one("#copyright-text")
            copyright_text.styles.background = scheme.footer_bg
            copyright_text.styles.color = scheme.cursor_bg  # Use accent color
        except Exception:
            pass

        # Apply to panels - this will also refresh their file lists with proper colors
        if self.left_panel:
            self.left_panel.set_color_scheme(scheme)

        if self.right_panel:
            self.right_panel.set_color_scheme(scheme)

        # Force a full screen refresh
        self.screen.refresh(repaint=True, layout=True)

    def update_panel_focus(self) -> None:
        """Update panel focus state."""
        if self.left_panel and self.right_panel:
            if self.active_panel == "left":
                self.left_panel.focus()
            else:
                self.right_panel.focus()

    def get_active_panel(self) -> FilePanel:
        """Get the currently active panel."""
        return self.left_panel if self.active_panel == "left" else self.right_panel

    def get_inactive_panel(self) -> FilePanel:
        """Get the currently inactive panel."""
        return self.right_panel if self.active_panel == "left" else self.left_panel

    def action_switch_panel(self) -> None:
        """Switch active panel."""
        self.active_panel = "right" if self.active_panel == "left" else "left"
        self.update_panel_focus()

    def action_refresh(self) -> None:
        """Refresh both panels."""
        if self.left_panel:
            self.left_panel.refresh_file_list()
        if self.right_panel:
            self.right_panel.refresh_file_list()

    def action_toggle_hidden(self) -> None:
        """Toggle showing hidden files."""
        self.show_hidden = not self.show_hidden
        self.config.set("show_hidden", self.show_hidden)

        # Update panels to use new setting
        if self.left_panel:
            self.left_panel.show_hidden = self.show_hidden
            self.left_panel.refresh_file_list()
        if self.right_panel:
            self.right_panel.show_hidden = self.show_hidden
            self.right_panel.refresh_file_list()

        status = "shown" if self.show_hidden else "hidden"
        self.notify(f"Hidden files are now {status}")

    def switch_to_theme(self, theme_name: str) -> None:
        """Switch to a specific theme."""
        self.theme_manager.current_theme = theme_name
        self.config.set_theme(theme_name)
        self.apply_theme()
        self.notify(f"Theme changed to: {theme_name}")

    def action_toggle_theme(self) -> None:
        """Cycle through available themes."""
        themes = self.theme_manager.get_available_themes()
        current_index = themes.index(self.theme_manager.current_theme)
        next_index = (current_index + 1) % len(themes)
        next_theme = themes[next_index]
        self.switch_to_theme(next_theme)

    def action_help(self) -> None:
        """Show help information."""
        self.notify("Help: Use arrow keys to navigate, Tab to switch panels, F-keys for operations")

    def action_view(self) -> None:
        """View the selected file."""
        panel = self.get_active_panel()
        if not panel:
            return

        item = panel.get_focused_item()
        if item and not item.is_dir:
            self.push_screen(FileViewerScreen(item.file_path))
        elif item and item.is_dir:
            self.notify("Cannot view directory", severity="warning")

    def action_edit(self) -> None:
        """Edit the selected file."""
        panel = self.get_active_panel()
        if not panel:
            return

        item = panel.get_focused_item()
        if item and not item.is_dir:
            editor = self.config.get("editor", "notepad.exe")
            try:
                import subprocess
                subprocess.Popen([editor, str(item.file_path)])
                self.notify(f"Opening in {editor}: {item.filename}")
            except Exception as e:
                self.notify(f"Error opening file: {e}", severity="error")

    def action_copy(self) -> None:
        """Copy file(s) from active to inactive panel."""
        active_panel = self.get_active_panel()
        inactive_panel = self.get_inactive_panel()

        if not active_panel or not inactive_panel:
            self.notify("Panels not available", severity="error")
            return

        # Get items to copy - either selected items or focused item
        selected_items = active_panel.get_selected_items()
        if selected_items:
            # Copy multiple selected items
            success_count = 0
            failed_count = 0
            for item_path in selected_items:
                dst = Path(inactive_panel.current_path) / item_path.name
                if self.file_ops.copy_file(item_path, dst):
                    self.undo_manager.record_copy(item_path, dst)
                    success_count += 1
                else:
                    failed_count += 1

            active_panel.clear_selection()
            inactive_panel.refresh_file_list()
            self.notify(f"Copied {success_count} items, {failed_count} failed")
        else:
            # Copy single focused item
            item = active_panel.get_focused_item()
            if item and item.filename != "..":
                dst = Path(inactive_panel.current_path) / item.filename
                if self.file_ops.copy_file(item.file_path, dst):
                    self.undo_manager.record_copy(item.file_path, dst)
                    self.notify(f"Copied: {item.filename}")
                    inactive_panel.refresh_file_list()
                else:
                    self.notify(f"Failed to copy: {item.filename}", severity="error")

    def action_move(self) -> None:
        """Move file(s) from active to inactive panel."""
        active_panel = self.get_active_panel()
        inactive_panel = self.get_inactive_panel()

        if not active_panel or not inactive_panel:
            self.notify("Panels not available", severity="error")
            return

        # Get items to move - either selected items or focused item
        selected_items = active_panel.get_selected_items()
        if selected_items:
            # Move multiple selected items
            success_count = 0
            failed_count = 0
            for item_path in selected_items:
                dst = Path(inactive_panel.current_path) / item_path.name
                if self.file_ops.move_file(item_path, dst):
                    self.undo_manager.record_move(item_path, dst)
                    success_count += 1
                else:
                    failed_count += 1

            active_panel.clear_selection()
            active_panel.refresh_file_list()
            inactive_panel.refresh_file_list()
            self.notify(f"Moved {success_count} items, {failed_count} failed")
        else:
            # Move single focused item
            item = active_panel.get_focused_item()
            if item and item.filename != "..":
                dst = Path(inactive_panel.current_path) / item.filename
                if self.file_ops.move_file(item.file_path, dst):
                    self.undo_manager.record_move(item.file_path, dst)
                    self.notify(f"Moved: {item.filename}")
                    active_panel.refresh_file_list()
                    inactive_panel.refresh_file_list()
                else:
                    self.notify(f"Failed to move: {item.filename}", severity="error")

    def action_mkdir(self) -> None:
        """Create a new directory."""
        panel = self.get_active_panel()
        if not panel:
            self.notify("No active panel", severity="error")
            return

        def check_result(dirname: str | None) -> None:
            if dirname:
                new_dir = Path(panel.current_path) / dirname
                if self.file_ops.create_directory(new_dir):
                    self.undo_manager.record_mkdir(new_dir)
                    self.notify(f"Created directory: {dirname}")
                    panel.refresh_file_list()
                else:
                    self.notify(f"Failed to create directory: {dirname}", severity="error")

        self.push_screen(
            InputDialog("Create Directory", "Enter directory name:"),
            check_result
        )

    def action_delete(self) -> None:
        """Delete the selected file(s)."""
        panel = self.get_active_panel()
        if not panel:
            return

        # Get items to delete - either selected items or focused item
        selected_items = panel.get_selected_items()
        if selected_items:
            # Delete multiple selected items
            self._delete_multiple_items(panel, selected_items)
        else:
            # Delete single focused item
            item = panel.get_focused_item()
            if item and item.filename != "..":
                self._delete_single_item(panel, item)

    def _delete_single_item(self, panel, item) -> None:
        """Delete a single item with confirmation."""
        def handle_confirm(result):
            if result == "yes":
                # Backup for undo before deleting
                self.undo_manager.record_delete(item.file_path)
                if self.file_ops.delete_file(item.file_path):
                    self.notify(f"Deleted: {item.filename}")
                    panel.refresh_file_list()
                else:
                    self.notify(f"Failed to delete: {item.filename}", severity="error")

        item_type = "directory" if item.is_dir else "file"
        self.push_screen(
            ConfirmDialog(
                "Confirm Delete",
                f"Delete {item_type}: {item.filename}?",
                show_all=False
            ),
            handle_confirm
        )

    def _delete_multiple_items(self, panel, items: list[Path]) -> None:
        """Delete multiple items with confirmation."""
        total_items = len(items)
        deleted_count = 0
        failed_count = 0
        delete_all = False

        def delete_next(index=0):
            nonlocal deleted_count, failed_count, delete_all

            if index >= total_items:
                # Done deleting
                panel.clear_selection()
                panel.refresh_file_list()
                self.notify(f"Deleted {deleted_count} items, {failed_count} failed")
                return

            item_path = items[index]
            item_name = item_path.name
            item_type = "directory" if item_path.is_dir() else "file"

            def handle_confirm(result):
                nonlocal deleted_count, failed_count, delete_all

                if result == "no":
                    # Skip this item
                    delete_next(index + 1)
                elif result in ("yes", "all"):
                    if result == "all":
                        delete_all = True

                    # Backup for undo before deleting
                    self.undo_manager.record_delete(item_path)
                    # Delete the item
                    if self.file_ops.delete_file(item_path):
                        deleted_count += 1
                    else:
                        failed_count += 1

                    delete_next(index + 1)

            # Show confirmation unless "Yes to All" was selected
            if delete_all:
                # Backup for undo before deleting
                self.undo_manager.record_delete(item_path)
                if self.file_ops.delete_file(item_path):
                    deleted_count += 1
                else:
                    failed_count += 1
                delete_next(index + 1)
            else:
                self.push_screen(
                    ConfirmDialog(
                        f"Confirm Delete ({index + 1}/{total_items})",
                        f"Delete {item_type}: {item_name}?",
                        show_all=True
                    ),
                    handle_confirm
                )

        delete_next()

    def action_menu(self) -> None:
        """Show main menu."""
        self.action_command_palette()

    def action_undo(self) -> None:
        """Undo the last action."""
        if not self.undo_manager.can_undo():
            self.notify("Nothing to undo")
            return

        success, message = self.undo_manager.undo()
        if success:
            self.notify(message)
            # Refresh both panels
            if self.left_panel:
                self.left_panel.refresh_file_list()
            if self.right_panel:
                self.right_panel.refresh_file_list()
        else:
            self.notify(message, severity="error")

    def action_rename(self) -> None:
        """Rename the selected file or directory."""
        panel = self.get_active_panel()
        if not panel:
            self.notify("No active panel", severity="error")
            return

        item = panel.get_focused_item()
        if not item or item.filename == "..":
            self.notify("Select a file or directory to rename", severity="warning")
            return

        def check_result(new_name: str | None) -> None:
            if new_name and new_name != item.filename:
                old_path = item.file_path
                new_path = old_path.parent / new_name
                if self.file_ops.rename_file(old_path, new_name):
                    self.undo_manager.record_rename(old_path, new_path)
                    self.notify(f"Renamed: {item.filename} -> {new_name}")
                    panel.refresh_file_list()
                else:
                    self.notify(f"Failed to rename: {item.filename}", severity="error")

        self.push_screen(
            InputDialog("Rename", f"Rename '{item.filename}' to:", item.filename),
            check_result
        )

    def action_sort(self) -> None:
        """Show sort options dialog."""
        def handle_sort(sort_order: str | None) -> None:
            if sort_order:
                self.current_sort = sort_order
                self.config.set("sort_order", sort_order)
                # Apply to both panels
                if self.left_panel:
                    self.left_panel.sort_order = sort_order
                    self.left_panel.refresh_file_list()
                if self.right_panel:
                    self.right_panel.sort_order = sort_order
                    self.right_panel.refresh_file_list()
                self.notify(f"Sort order: {sort_order.replace('_', ' ')}")

        self.push_screen(
            SortDialog(self.current_sort),
            handle_sort
        )

    def action_goto_drives(self) -> None:
        """Navigate the active panel to This PC (drives view)."""
        panel = self.get_active_panel()
        if panel:
            panel.go_to_this_pc()
            self.notify("Navigated to This PC")

    def on_file_panel_path_changed(self, message: FilePanel.PathChanged) -> None:
        """Handle path changes in panels."""
        if message.control == self.left_panel:
            self.config.set("left_panel_path", message.path)
        elif message.control == self.right_panel:
            self.config.set("right_panel_path", message.path)

    def on_descendant_focus(self, event) -> None:
        """Track which panel has focus."""
        # Check if the focused widget or any of its ancestors is a panel
        widget = event.widget
        while widget is not None:
            if hasattr(widget, 'id'):
                if widget.id == "left-panel":
                    self.active_panel = "left"
                    return
                elif widget.id == "right-panel":
                    self.active_panel = "right"
                    return
            widget = widget.parent


def main():
    """Main entry point."""
    app = MoCommander()
    app.run()


if __name__ == "__main__":
    main()
