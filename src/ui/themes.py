"""Theme system for Mo Commander with customizable color schemes."""

from dataclasses import dataclass
from typing import Dict
from textual.theme import Theme


@dataclass
class ColorScheme:
    """Color scheme for the application."""

    panel_bg: str
    panel_fg: str
    panel_border: str
    selected_bg: str
    selected_fg: str
    header_bg: str
    header_fg: str
    footer_bg: str
    footer_fg: str
    cursor_bg: str
    cursor_fg: str
    directory_fg: str
    executable_fg: str
    archive_fg: str


# MC color schemes (our internal representation)
MC_SCHEMES: Dict[str, ColorScheme] = {
    "classic": ColorScheme(
        panel_bg="#0000aa",
        panel_fg="#00ffff",
        panel_border="#ffffff",
        selected_bg="#00ffff",
        selected_fg="#000000",
        header_bg="#00ffff",
        header_fg="#000000",
        footer_bg="#000000",
        footer_fg="#ffffff",
        cursor_bg="#00aa00",
        cursor_fg="#000000",
        directory_fg="#ffff00",
        executable_fg="#00ff00",
        archive_fg="#ff00ff",
    ),
    "dark": ColorScheme(
        panel_bg="#1e1e1e",
        panel_fg="#d4d4d4",
        panel_border="#3e3e3e",
        selected_bg="#264f78",
        selected_fg="#ffffff",
        header_bg="#007acc",
        header_fg="#ffffff",
        footer_bg="#000000",
        footer_fg="#ffffff",
        cursor_bg="#0e639c",
        cursor_fg="#ffffff",
        directory_fg="#4ec9b0",
        executable_fg="#4fc1ff",
        archive_fg="#c586c0",
    ),
    "light": ColorScheme(
        panel_bg="#ffffff",
        panel_fg="#000000",
        panel_border="#cccccc",
        selected_bg="#0078d4",
        selected_fg="#ffffff",
        header_bg="#f3f3f3",
        header_fg="#000000",
        footer_bg="#000000",
        footer_fg="#ffffff",
        cursor_bg="#0078d4",
        cursor_fg="#ffffff",
        directory_fg="#0066cc",
        executable_fg="#008000",
        archive_fg="#800080",
    ),
    "retro": ColorScheme(
        panel_bg="#000080",
        panel_fg="#00ffff",
        panel_border="#ffff00",
        selected_bg="#00ffff",
        selected_fg="#000080",
        header_bg="#00ffff",
        header_fg="#000080",
        footer_bg="#000000",
        footer_fg="#00ffff",
        cursor_bg="#00ff00",
        cursor_fg="#000000",
        directory_fg="#ffff00",
        executable_fg="#00ff00",
        archive_fg="#ff00ff",
    ),
    "monokai": ColorScheme(
        panel_bg="#272822",
        panel_fg="#f8f8f2",
        panel_border="#75715e",
        selected_bg="#49483e",
        selected_fg="#f8f8f2",
        header_bg="#3e3d32",
        header_fg="#f8f8f2",
        footer_bg="#000000",
        footer_fg="#f8f8f2",
        cursor_bg="#66d9ef",
        cursor_fg="#272822",
        directory_fg="#66d9ef",
        executable_fg="#a6e22e",
        archive_fg="#ae81ff",
    ),
}


def create_textual_theme(name: str, scheme: ColorScheme) -> Theme:
    """Create a Textual Theme from our ColorScheme."""
    return Theme(
        name=f"mc-{name}",
        primary=scheme.cursor_bg,
        secondary=scheme.selected_bg,
        background=scheme.panel_bg,
        surface=scheme.panel_bg,
        panel=scheme.panel_bg,
        foreground=scheme.panel_fg,
        dark=True,  # Most of our themes are dark
        variables={
            # Block cursor (highlight) colors - this is what controls the ListView highlight
            "block-cursor-background": scheme.cursor_bg,
            "block-cursor-foreground": scheme.cursor_fg,
            "block-cursor-text-style": "bold",
            "block-cursor-blurred-background": scheme.selected_bg,
            "block-cursor-blurred-foreground": scheme.selected_fg,
            "block-cursor-blurred-text-style": "none",
            # Footer styling
            "footer-background": scheme.footer_bg,
            "footer-key-foreground": scheme.cursor_bg,
            "footer-description-foreground": scheme.footer_fg,
            # Border colors
            "border": scheme.panel_border,
            "border-blurred": scheme.panel_border,
            # Scrollbar
            "scrollbar-background": scheme.panel_bg,
            "scrollbar": scheme.panel_border,
        },
    )


# Create Textual themes from our schemes
MC_TEXTUAL_THEMES: Dict[str, Theme] = {
    name: create_textual_theme(name, scheme)
    for name, scheme in MC_SCHEMES.items()
}


class ThemeManager:
    """Manages application themes."""

    THEMES = MC_SCHEMES

    def __init__(self, theme_name: str = "retro"):
        self._current_theme = theme_name if theme_name in self.THEMES else "retro"

    @property
    def current_theme(self) -> str:
        """Get the current theme name."""
        return self._current_theme

    @current_theme.setter
    def current_theme(self, theme_name: str) -> None:
        """Set the current theme."""
        if theme_name not in self.THEMES:
            raise ValueError(f"Theme '{theme_name}' not found")
        self._current_theme = theme_name

    def get_scheme(self) -> ColorScheme:
        """Get the current color scheme."""
        return self.THEMES[self._current_theme]

    def get_textual_theme(self) -> Theme:
        """Get the current Textual theme."""
        return MC_TEXTUAL_THEMES[self._current_theme]

    def get_textual_theme_name(self) -> str:
        """Get the Textual theme name for the current theme."""
        return f"mc-{self._current_theme}"

    def get_available_themes(self) -> list[str]:
        """Get list of available theme names."""
        return list(self.THEMES.keys())

    @staticmethod
    def get_all_textual_themes() -> Dict[str, Theme]:
        """Get all Textual themes for registration."""
        return MC_TEXTUAL_THEMES
