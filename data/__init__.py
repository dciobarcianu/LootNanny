import json
import os

from helpers import resource_path


LEGACY_ATTACHMENT_NAMES = {
    "Mayhem MF-Amplfier Alpha (L)": "Mayhem MF-Amplifier Alpha (L)",
}


def load_data_file(filename):
    path = resource_path(filename)
    if not os.path.isfile(path):
        path = resource_path(os.path.join("data", "raw", filename))

    with open(path, "r", encoding="utf-8") as source:
        contents = json.load(source)

    if isinstance(contents, dict) and "updated" in contents and "data" in contents:
        contents = contents["data"]
    if not isinstance(contents, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return contents