import json
import os
import xml.etree.ElementTree as ET


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_JSON_TITLE = "Credits.json"


def clean_text(value):
    return (value or "").strip()


def read_xml_text(path):
    data = open(path, "rb").read()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def convert_data():
    xml_text = read_xml_text(os.path.join(BASE_DIR, "metas", "credits.xml"))
    root = ET.fromstring(xml_text)
    categories = []

    for category in root.findall("category"):
        name = clean_text(category.get("name"))
        entries = [clean_text(entry.text) for entry in category.findall("entry")]
        entries = [entry for entry in entries if entry]
        if not name and not entries:
            continue
        categories.append({
            "name": name,
            "entries": entries,
        })

    return categories


def convert():
    return json.dumps(convert_data(), ensure_ascii=False, separators=(",", ":"))

