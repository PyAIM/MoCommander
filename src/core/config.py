"""Configuration management for Mo Commander."""

import json
import os
from pathlib import Path
from typing import Dict, Any


class Config:
    """Application configuration manager."""

    DEFAULT_CONFIG = {
        "theme": "retro",
        "show_hidden": False,
        "left_panel_path": None,
        "right_panel_path": None,
        "confirm_operations": True,
        "editor": "notepad.exe",
        "sort_order": "name_asc",
    }

    def __init__(self):
        self.config_dir = Path.home() / ".mocommander"
        self.config_file = self.config_dir / "config.json"
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    self._config = {**self.DEFAULT_CONFIG, **json.load(f)}
            except (json.JSONDecodeError, IOError):
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()

    def save(self) -> None:
        """Save configuration to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, "w") as f:
                json.dump(self._config, f, indent=2)
        except IOError:
            pass

    def get(self, key: str, default=None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self._config[key] = value
        self.save()

    def get_theme(self) -> str:
        """Get current theme name."""
        return self._config.get("theme", "retro")

    def set_theme(self, theme: str) -> None:
        """Set current theme."""
        self.set("theme", theme)

    def get_left_panel_path(self) -> str:
        """Get left panel path."""
        return self._config.get("left_panel_path") or os.getcwd()

    def get_right_panel_path(self) -> str:
        """Get right panel path."""
        return self._config.get("right_panel_path") or os.getcwd()
