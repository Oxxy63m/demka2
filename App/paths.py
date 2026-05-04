from __future__ import annotations

import os

from App.config import DATA_DIR


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ui_dir() -> str:
    return os.path.join(project_root(), "UI")


def resources_dir() -> str:
    return os.path.join(project_root(), DATA_DIR)


def app_images_dir() -> str:
    d = os.path.join(project_root(), "app_images")
    os.makedirs(d, exist_ok=True)
    return d


def ui_path(filename: str) -> str:
    return os.path.join(ui_dir(), filename)


def resource_path(filename: str) -> str:
    return os.path.join(resources_dir(), filename)


def icon_path() -> str:
    # В ресурсах есть Icon.png
    return resource_path("Icon.png")


def logo_path_fallback() -> str:
    # Явного logo нет — используем Icon.png
    return icon_path()

