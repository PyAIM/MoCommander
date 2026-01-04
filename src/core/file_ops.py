"""File operations for Mo Commander."""

import os
import shutil
from pathlib import Path
from typing import Optional


class FileOperations:
    """File operations handler."""

    @staticmethod
    def copy_file(src: Path, dst: Path) -> bool:
        """Copy a file from src to dst."""
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    @staticmethod
    def move_file(src: Path, dst: Path) -> bool:
        """Move a file from src to dst."""
        try:
            shutil.move(str(src), str(dst))
            return True
        except Exception:
            return False

    @staticmethod
    def delete_file(path: Path) -> bool:
        """Delete a file or directory."""
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
        except Exception:
            return False

    @staticmethod
    def create_directory(path: Path) -> bool:
        """Create a new directory."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    @staticmethod
    def rename_file(src: Path, new_name: str) -> bool:
        """Rename a file or directory."""
        try:
            dst = src.parent / new_name
            src.rename(dst)
            return True
        except Exception:
            return False

    @staticmethod
    def get_file_info(path: Path) -> Optional[dict]:
        """Get file information."""
        try:
            stat = path.stat()
            return {
                "name": path.name,
                "size": stat.st_size,
                "is_dir": path.is_dir(),
                "modified": stat.st_mtime,
                "created": stat.st_ctime,
            }
        except Exception:
            return None
