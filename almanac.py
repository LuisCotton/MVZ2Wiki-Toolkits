import ast
import json
import operator
import os
import re
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NS = "mvz2:"
VAR_RE = re.compile(r'<var\s+([^<>]*?)/?\s*>', re.I)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2')
REF_RE = re.compile(r'<ref=\[([^\]]+)\]([^>]+)>(.*?)</ref>', re.I | re.S)
INLINE_TAG_RE = re.compile(r'<tag\s+([^<>]*?)/\s*>', re.I)
ROTATE_RE = re.compile(r'</?rotate(?:=(?:"[^"]*"|\'[^\']*\'))?\s*>', re.I)
ALIGN_RE = re.compile(r'<align\s*=\s*(["\']?)([^"\'>\s]+)\1\s*>(.*?)</align>', re.I | re.S)
COLOR_RE = re.compile(r'<color\s*=\s*(["\']?)([^"\'>\s]+)\1\s*>(.*?)</color>', re.I | re.S)
WIKI_LINK_RE = re.compile(r'\[\[.*?]]', re.S)
HASH_LINE_RE = re.compile(r'^(#+)(.*?)(#+)$')
HTML_TAG_RE = re.compile(r'<[^>]+>')
WIKI_JSON_TITLE = "Almanac.json"


def short(value):
    return value[len(NS):] if isinstance(value, str) and value.startswith(NS) else value


def sprite_file(value):
    value = short(value or "")
    if not value:
        return ""
    return "mvz2_" + value.replace("/", ".") + ".png"


def parse(name):
    with open(os.path.join(BASE_DIR, "metas", name), encoding="utf-8-sig") as source:
        text = source.read()
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
        return ET.fromstring("<root>" + text + "</root>")


def parse_optional(name):
    path = os.path.join(BASE_DIR, "metas", name)
    if not os.path.exists(path):
        return None
    return parse(name)


def normalized_id(value):
    if not isinstance(value, str):
        return ""
    value = short(value.strip())
    return value.lower()


def load_armor_health():
    root = parse_optional("armors.xml")
    if root is None:
        return {}
    armors = {}
    for entry in root.findall(".//entry"):
        armor_id = normalized_id(entry.get("id"))
        if not armor_id or entry.get("ignored", "").lower() == "true":
            continue
        for prop in entry.findall(".//props/*") + entry.findall(".//properties/*"):
            if normalized_id(prop.get("name")) == "maxhealth" and prop.get("value") not in (None, ""):
                armors[armor_id] = prop.get("value")
                break
    return armors


def armor_value_ids(value):
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\s,;|]+", str(value))
    ids = []
    for part in parts:
        text = str(part).strip().strip("[](){}\"'")
        if not text:
            continue
        ids.append(text)
        if ":" in text:
            ids.append(text.rsplit(":", 1)[-1])
        if "/" in text:
            ids.append(text.rsplit("/", 1)[-1])
    return ids


def armor_properties(values, armor_health):
    if not armor_health:
        return {}
    armor_key_words = ("armor", "armour", "helmet", "helm", "shield", "hat", "cap", "crown")
    totals = {"armor_hp": 0.0, "shield_hp": 0.0}
    found = False
    for name, value in values.items():
        key = normalized_id(name)
        should_check = any(word in key for word in armor_key_words)
        candidate_ids = armor_value_ids(value)
        if not should_check and not any(normalized_id(armor_id) in armor_health for armor_id in candidate_ids):
            continue
        slot = "shield_hp" if "shield" in key else "armor_hp"
        for armor_id in candidate_ids:
            health = armor_health.get(normalized_id(armor_id))
            if health is None:
                continue
            try:
                totals[slot] += float(health)
            except ValueError:
                totals[slot] = str(health)
                found = True
                break
            found = True
        if found and isinstance(totals[slot], str):
            break
    if not found:
        return {}
    result = {}
    total = 0.0
    for name, value in totals.items():
        if isinstance(value, str):
            result[name] = value
            result["mvz2:" + name] = value
            continue
        if value == 0:
            continue
        text = str(int(value)) if value.is_integer() else str(value)
        result[name] = text
        result["mvz2:" + name] = text
        total += value
    if total:
        text = str(int(total)) if total.is_integer() else str(total)
        result["ARMOR"] = text
        result["mvz2:ARMOR"] = text
    return result


def inner_xml(element, strip=True):
    parts = [element.text or ""]
    parts.extend(ET.tostring(child, encoding="unicode") for child in element)
    value = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    return value.strip() if strip else value


def paragraphs(element, preserve_spaces=False):
    if element is None:
        return []
    values = [inner_xml(child, strip=not preserve_spaces) for child in element if child.tag == "p"]
    if values:
        return values
    text = inner_xml(element, strip=not preserve_spaces)
    return [text] if text else []


TAG_KINDS = {
    "placement": "放置条件",
    "grid_layer": "占据位",
    "shell": "材质",
    "mass": "质量",
    "attribute": "特性",
}


TAG_VALUE_ALIASES = {
    "placement_normal": "陆地器械",
    "placement_two_gravelpults": "沙砾投手",
    "light_source": "发光",
    "floor_contraption": "地面器械",
    "short_enemy": "低矮",
    "can_trigger": "可触发",
    "control_immunity": "控制免疫",
    "not_undead": "非亡灵",
}


SUPPORTED_TAG_VALUES = None


def supported_tag_values():
    global SUPPORTED_TAG_VALUES
    if SUPPORTED_TAG_VALUES is not None:
        return SUPPORTED_TAG_VALUES
    values = set()
    template_path = os.path.join(BASE_DIR, "template_tag_icon.wikitext")
    try:
        with open(template_path, encoding="utf-8-sig") as source:
            for line in source:
                stripped = line.strip()
                if not stripped.startswith("|") or "=" not in stripped:
                    continue
                left = stripped.split("=", 1)[0]
                for part in left.split("|"):
                    part = part.strip()
                    if part and not part.startswith("#"):
                        values.add(part)
    except OSError:
        pass
    SUPPORTED_TAG_VALUES = values
    return values


PROPERTY_TAGS = {
    "isLightSource": "light_source",
    "isFloor": "floor_contraption",
    "low_enemy": "short_enemy",
    "flying_enemy": "flying",
    "triggerActive": "can_trigger",
    "isFire": "fire",
}


def tag_template_args(definition, enum_value=None):
    if not definition:
        return "", ""
    tag_id = definition.get("id", "")
    kind_key = tag_id
    for prefix in ("placement_", "grid_layer_", "shell_", "mass_"):
        if tag_id.startswith(prefix):
            kind_key = prefix[:-1]
            break
    kind = TAG_KINDS.get(kind_key, TAG_KINDS["attribute"])
    if enum_value:
        enum_name = enum_value.get("name", "")
        definition_name = definition.get("name", "")
        if definition_name and definition_name != kind:
            composite_value = f"{definition_name}：{enum_name}"
            if composite_value in supported_tag_values():
                return kind, composite_value
        return kind, enum_name
    value = TAG_VALUE_ALIASES.get(tag_id, definition.get("name", ""))
    if value.startswith("升级器械："):
        value = value[len("升级器械："):]
    return kind, value


def tag_markup(definition, enum_value=None):
    kind, value = tag_template_args(definition, enum_value)
    if not kind or not value:
        return ""
    return f"{{{{标签图标|{kind}|{value}}}}}"


def normalize_markup(value, entity_names, tag_definitions=None, enums=None):
    value = ROTATE_RE.sub("", value)
    value = ALIGN_RE.sub(lambda match: f'<div style="text-align:{match.group(2)};">{match.group(3)}</div>', value)
    value = COLOR_RE.sub(lambda match: f'<span style="color:{match.group(2)};">{match.group(3)}</span>', value)
    value = HASH_LINE_RE.sub(lambda match: f"<nowiki>{match.group(1)}</nowiki>{match.group(2)}<nowiki>{match.group(3)}</nowiki>", value)

    def replace_ref(match):
        category, target, label = match.groups()
        if category.strip().lower() in ("contraptions", "enemies"):
            entity_id = short(target.strip())
            page = entity_names.get(entity_id) or entity_names.get(entity_id.lower()) or label
            return f"[[{page}]]" if page == label else f"[[{page}|{label}]]"
        return f"[[{label}]]"

    def replace_tag(match):
        tag_definitions_local = tag_definitions or {}
        enums_local = enums or {}
        attrs = {name: attr_value for name, _, attr_value in ATTR_RE.findall(match.group(1))}
        tag_id = short(attrs.get("id", ""))
        if not tag_id:
            return ""
        tag_value = short(attrs.get("enum") or attrs.get("value") or tag_id)
        definition = tag_definitions_local.get(tag_id)
        enum_value = None
        if definition and definition.get("enum"):
            enum_value = enums_local.get(definition.get("enum"), {}).get(tag_value)
            if enum_value:
                rendered = tag_markup(definition, enum_value)
                if rendered:
                    return rendered
        rendered = tag_markup(definition)
        if rendered:
            return rendered
        return f"{{{{标签图标|{tag_id}|{tag_value}}}}}"

    value = WIKI_LINK_RE.sub(lambda match: f"<nowiki>{match.group(0)}</nowiki>", value)
    value = REF_RE.sub(replace_ref, value)
    return INLINE_TAG_RE.sub(replace_tag, value)


def add_case_aliases(values):
    if not isinstance(values, dict):
        return values
    for name, value in list(values.items()):
        if not isinstance(name, str):
            continue
        values.setdefault(name.lower(), value)
        values.setdefault(name.upper(), value)
        if name.startswith(NS):
            suffix = name[len(NS):]
            values.setdefault(NS + suffix.lower(), value)
            values.setdefault(NS + suffix.upper(), value)
    return values


def properties(owner):
    result = {}
    for section in owner.iter():
        if section is owner or section.tag not in ("properties", "props"):
            continue
        behaviour = section.get("behaviour")
        for prop in section:
            name = prop.get("name")
            if not name:
                continue
            if behaviour:
                name = f"mvz2:entity_behaviour/{short(behaviour)}/{short(name)}"
            if "value" in prop.attrib:
                result[name] = prop.get("value", "")
            else:
                axes = [prop.get(axis) for axis in ("x", "y", "z", "w") if prop.get(axis) is not None]
                result[name] = axes if len(axes) > 1 else (axes[0] if axes else inner_xml(prop))
    return add_case_aliases(result)


def load_templates(root):
    section = root.find("templates")
    return {
        child.tag: {
            "parent": child.get("parent"),
            "type": child.get("type"),
            "properties": properties(child),
        }
        for child in (list(section) if section is not None else [])
    }


def inherited(name, all_templates, cache, stack=()):
    if not name or name not in all_templates:
        return {}, None
    if name in cache:
        return cache[name]
    if name in stack:
        raise ValueError("模板循环继承：" + " -> ".join(stack + (name,)))
    template = all_templates[name]
    values, entity_type = inherited(template["parent"], all_templates, cache, stack + (name,))
    values = dict(values)
    values.update(template["properties"])
    entity_type = template["type"] or entity_type
    cache[name] = values, entity_type
    return cache[name]


def load_entities(root, all_templates):
    result = {}
    cache = {}
    section = root.find("entries")
    for entry in (list(section) if section is not None else []):
        entity_id = short(entry.get("id", ""))
        if not entity_id:
            continue
        values, entity_type = inherited(entry.get("template"), all_templates, cache)
        values = dict(values)
        values.update(properties(entry))
        result[entity_id] = {
            "id": entity_id,
            "name": entry.get("name", entity_id),
            "type": entity_type,
            "properties": values,
        }
    return result


def variable_map(element):
    if element is None:
        return {}
    result = {}
    for item in element:
        key = short(item.get("id") or item.get("name") or "")
        if key:
            result[key] = item.get("value") or inner_xml(item)
    return result


def load_almanac(root):
    result = {}
    section = root.find("contraptions")
    for entry in (list(section) if section is not None else []):
        entry_id = short(entry.get("id", ""))
        if not entry_id:
            continue
        flavors = []
        direct = entry.find("flavor")
        if direct is not None:
            flavors.extend(paragraphs(direct, preserve_spaces=True))
        group = entry.find("flavors")
        if group is not None:
            for flavor in group.findall("flavor"):
                flavors.extend(paragraphs(flavor, preserve_spaces=True))
        tags = [
            {"id": short(tag.get("id", "")), "value": tag.get("value") or tag.get("enum")}
            for tag in entry.findall("./tags/tag") if tag.get("id")
        ]
        result[entry_id] = {
            "id": entry_id,
            "header": paragraphs(entry.find("header")),
            "properties": paragraphs(entry.find("properties")),
            "flavor": flavors,
            "variables": variable_map(entry.find("variables")),
            "sourceTags": tags,
        }
    return result


def load_tag_definitions(root):
    result = {}
    section = root.find("tags")
    for tag in (list(section) if section is not None else []):
        if tag.tag != "tag":
            continue
        tag_id = short(tag.get("id", ""))
        if tag_id:
            icon = tag.find("icon")
            background = tag.find("background")
            mark = tag.find("mark")
            result[tag_id] = {
                "id": tag_id,
                "name": tag.get("name", ""),
                "description": tag.get("description", ""),
                "enum": short(tag.get("enum", "")),
                "priority": int(tag.get("priority", "4000")),
                "icon": sprite_file(icon.get("sprite")) if icon is not None else "",
                "background": sprite_file(background.get("sprite")) if background is not None else "",
                "backgroundColor": background.get("color", "") if background is not None else "",
                "mark": sprite_file(mark.get("sprite")) if mark is not None else "",
            }
    return result


def load_enums(root):
    result = {}
    section = root.find("tags")
    for enum in (list(section) if section is not None else []):
        if enum.tag != "enum":
            continue
        enum_id = short(enum.get("id", ""))
        values = {}
        for value in enum.findall("value"):
            key = short(value.get("value", ""))
            if key:
                values[key] = {
                    "value": key,
                    "name": value.get("name", ""),
                    "description": value.get("description", ""),
                    "icon": sprite_file(value.get("sprite")),
                    "backgroundColor": value.get("backgroundColor", ""),
                }
        if enum_id and values:
            result[enum_id] = values
    return result


class Resolver:
    OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def __init__(self, entries, globals_raw):
        self.entries = entries
        self.globals_raw = globals_raw
        self.cache = {}
        self.active = set()

    def resolve(self, expression, owner):
        expression = (expression or "").strip()
        if not expression:
            return ""
        expression = self.calls(expression, "local", lambda args: self.local(owner, args[0]) if args else "")
        expression = self.calls(expression, "global", lambda args: self.global_value(owner, args[0]) if args else "")
        expression = self.calls(expression, "property", lambda args: self.property(owner, args))
        expression = self.calls(expression, "toDouble", lambda args: args[0] if args else "")
        if any(token in expression for token in ("property(", "global(", "local(", "toDouble(")):
            return ""
        return self.calculate(expression)

    def calls(self, text, name, callback):
        marker = name + "("
        while marker in text:
            start = text.rfind(marker)
            end = self.closing(text, start + len(name))
            if end < 0:
                return text
            args = self.arguments(text[start + len(marker):end])
            value = str(callback(args))
            try:
                float(value)
                replacement = value
            except ValueError:
                replacement = json.dumps(value, ensure_ascii=False)
            text = text[:start] + replacement + text[end + 1:]
        return text

    @staticmethod
    def closing(text, opening):
        depth = 0
        quote = None
        for index in range(opening, len(text)):
            char = text[index]
            if quote:
                if char == quote and text[index - 1] != "\\":
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        return -1

    @staticmethod
    def arguments(text):
        try:
            return list(ast.literal_eval("[" + text + "]"))
        except (SyntaxError, ValueError):
            return [text.strip().strip("\"'")] if text.strip() else []

    def local(self, owner, name):
        return self.named(owner, "local", short(name), self.entries.get(owner, {}).get("variables", {}))

    def global_value(self, owner, name):
        return self.named(owner, "global", short(name), self.globals_raw)

    def named(self, owner, scope, name, source):
        key = owner, scope, name
        if key in self.cache:
            return self.cache[key]
        if key in self.active or name not in source:
            return ""
        self.active.add(key)
        value = self.resolve(source[name], owner)
        self.active.remove(key)
        self.cache[key] = value
        return value

    def property(self, owner, args):
        if not args:
            return ""
        path = str(args[0])
        target = short(str(args[1])) if len(args) > 1 and args[1] else owner
        domain = str(args[2]).lower() if len(args) > 2 else "entity"
        if domain != "entity":
            return ""
        values = self.entries.get(target, {}).get("entityProperties", {})
        candidates = [path]
        if path.startswith("mvz2:entity/"):
            candidates.append("mvz2:" + path.split("/", 1)[1])
        for candidate in candidates:
            value = values.get(candidate)
            if isinstance(value, str):
                return value
        return ""

    def calculate(self, expression):
        text = expression.strip()
        if not text:
            return ""
        try:
            tree = ast.parse(text, mode="eval")
            value = self.node(tree.body)
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            return str(value)
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
            return text.strip("\"'")

    def node(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self.OPS:
            return self.OPS[type(node.op)](self.node(node.left), self.node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.OPS:
            return self.OPS[type(node.op)](self.node(node.operand))
        raise ValueError("不支持的表达式")


def replace_vars(value, globals_values, locals_values):
    if isinstance(value, list):
        return [replace_vars(item, globals_values, locals_values) for item in value]

    def replace(match):
        attrs = {key: val for key, _, val in ATTR_RE.findall(match.group(1))}
        variable = short(attrs.get("local") or attrs.get("id", ""))
        resolved = locals_values.get(variable, globals_values.get(variable, ""))
        if not resolved and variable in ("armor_hp", "helmet_hp", "shield_hp"):
            return "\x00ARMOR\x00"
        multiplier = attrs.get("mult")
        if resolved and multiplier:
            resolved = Resolver({}, {}).calculate(f"({resolved})*({multiplier})")
        return resolved

    value = VAR_RE.sub(replace, value)
    return re.sub(r"\+?\x00ARMOR\x00（[^）]*）", "", value)


def snake_case(value):
    value = short(str(value or ""))
    value = value.rsplit("/", 1)[-1]
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    return value.strip("_").lower()


def property_tag_candidates(prop):
    name = snake_case(prop)
    candidates = [name]
    for prefix in ("is_", "can_", "has_"):
        if name.startswith(prefix):
            candidates.append(name[len(prefix):])
    return candidates


def make_tags(item, tag_definitions=None, enums=None):
    tag_definitions = tag_definitions or {}
    enums = enums or {}
    result = []
    seen = set()

    def add(definition, enum_value=None, priority=None):
        if not definition:
            return
        kind, tag_value = tag_template_args(definition, enum_value)
        record = {
            "id": definition.get("id", ""),
            "kind": kind,
            "value": tag_value,
            "name": definition.get("name", ""),
            "description": definition.get("description", ""),
            "icon": definition.get("icon", ""),
            "background": definition.get("background", ""),
            "backgroundColor": definition.get("backgroundColor", ""),
            "mark": definition.get("mark", ""),
        }
        if enum_value:
            record["name"] = (definition.get("name", "") + "：" if definition.get("name") else "") + enum_value.get("name", "")
            record["description"] = enum_value.get("description", "") or definition.get("description", "")
            record["icon"] = enum_value.get("icon", "") or definition.get("icon", "")
            record["backgroundColor"] = enum_value.get("backgroundColor", "") or definition.get("backgroundColor", "")
        key = record.get("kind", ""), record.get("value", "")
        if record.get("kind") and record.get("value") and key not in seen:
            seen.add(key)
            result.append((priority if priority is not None else definition.get("priority", 4000), record))

    def add_by_id(tag_id, value=None, priority=None):
        tag_id = short(tag_id or "")
        if tag_id == "placement_normal":
            tag_id = "placement_land"
        tag_id = PROPERTY_TAGS.get(tag_id, tag_id)
        definition = tag_definitions.get(tag_id)
        if not definition:
            return
        enum_id = definition.get("enum", "")
        enum_value = None
        if enum_id:
            enum_value = enums.get(enum_id, {}).get(short(str(value or "")))
            if not enum_value:
                return
        add(definition, enum_value, priority)

    values = item.get("entityProperties", {})
    placement = short(values.get("mvz2:placement", ""))
    add_by_id("placement_" + placement)

    grid_layers = values.get("mvz2:gridLayers", "")
    grid_layers = grid_layers if isinstance(grid_layers, list) else re.split(r"[\s,;|]+", grid_layers)
    for layer in grid_layers:
        add_by_id("grid_layer_" + short(str(layer)))

    shell = short(values.get("mvz2:shell", ""))
    add_by_id("shell", shell)

    for source in item.get("sourceTags", []):
        tag_id = short(source["id"])
        value = short(source.get("value") or tag_id)
        add_by_id(tag_id, value)

    mass = short(str(values.get("mvz2:mass", "")))
    if item.get("type") == "enemy" and not mass:
        mass = "0"
    add_by_id("mass", mass, 2500)
    category = short(values.get("mvz2:Category", ""))
    add_by_id("category", category, 2600)

    for prop, prop_value in values.items():
        if str(prop_value).lower() != "true":
            continue
        raw_prop = short(prop).rsplit("/", 1)[-1]
        add_by_id(PROPERTY_TAGS.get(raw_prop, raw_prop))
        for candidate in property_tag_candidates(prop):
            before = len(seen)
            add_by_id(candidate)
            if len(seen) != before:
                break
    for prop, prop_value in values.items():
        if str(prop_value).lower() != "false":
            continue
        name = snake_case(prop)
        for candidate in ("not_" + name, "non_" + name):
            before = len(seen)
            add_by_id(candidate)
            if len(seen) != before:
                break
    result.sort(key=lambda value: value[0])
    return [value for _, value in result[:15]]


def compact(item, tag_definitions=None, enums=None):
    result = {"id": item["id"], "name": item.get("name", item["id"])}
    for key in ("header", "properties", "flavor"):
        values = [value for value in item.get(key, []) if value]
        if values:
            result[key] = values[0] if len(values) == 1 else values
    if item.get("cost") not in (None, "", "0", 0):
        result["cost"] = item["cost"]
    if item.get("rechargeId") not in (None, "", "none", "mvz2:none"):
        result["recharge"] = short(item["rechargeId"])
    tags = make_tags(item, tag_definitions, enums)
    if tags:
        result["tags"] = tags
    fields = almanac_fields(item.get("properties", []))
    if fields:
        result["almanacFields"] = fields
    entity_properties = item.get("entityProperties", {})
    wanted_properties = {
        "mvz2:maxHealth": "toughness",
        "mvz2:cost": "cost",
        "mvz2:rechargeId": "rechargeId",
        "mvz2:gridLayers": "gridLayers",
        "mvz2:shell": "shell",
        "mvz2:range": "range",
        "mvz2:damage": "damage",
        "mvz2:attackSpeed": "attackSpeed",
        "mvz2:produceSpeed": "produceSpeed",
    }
    infobox = {}
    for source, target in wanted_properties.items():
        value = entity_properties.get(source)
        if value not in (None, ""):
            infobox[target] = value
    if infobox:
        result["infobox"] = infobox
    return result


def plain_text(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("<br>", "\n")
    value = HTML_TAG_RE.sub("", value)
    return value.strip()


def almanac_fields(properties):
    result = {}
    mapping = {
        "耐久": "toughness",
        "发射速度": "firerate",
        "攻速": "firerate",
        "攻击速度": "firerate",
        "伤害": "damage",
        "生产时间": "producetime",
        "生产速度": "producetime",
        "提供能量": "production",
        "特点": "special",
        "技能": "evocation",
    }
    if isinstance(properties, str):
        properties = [properties]
    for line in properties or []:
        text = plain_text(line)
        if "：" not in text:
            continue
        label, value = text.split("：", 1)
        key = mapping.get(label.strip())
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def meta_xml_root(path):
    with open(path, encoding="utf-8-sig") as source:
        text = source.read()
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
        return ET.fromstring("<root>" + text + "</root>")


def meta_node_id(node):
    for key in (
        "id", "name", "entity", "entityId", "entityID", "entityType",
        "type", "entity_id", "entityName", "entityNameID",
    ):
        value = node.get(key)
        if value:
            return value
    return None


def meta_node_properties(node):
    result = {key: value for key, value in node.attrib.items() if key not in ("id", "name")}
    for child in node:
        name = child.get("name") or child.get("id")
        if not name:
            continue
        if "value" in child.attrib:
            result[name] = child.get("value")
        elif child.text and child.text.strip() and len(child) == 0:
            result[name] = child.text.strip()
        else:
            child_values = {key: value for key, value in child.attrib.items() if key not in ("id", "name")}
            if child_values:
                result[name] = child_values.get("value", child_values)
    return add_case_aliases(result)


def load_meta_entity_properties(all_entities):
    metas_dir = os.path.join(BASE_DIR, "metas")
    result = {entity_id: {} for entity_id in all_entities}
    if not os.path.isdir(metas_dir):
        return result

    aliases = {}
    for entity_id in all_entities:
        names = {entity_id, entity_id.lower(), short(entity_id), short(entity_id).lower(), NS + short(entity_id), (NS + short(entity_id)).lower()}
        for name in names:
            aliases[name] = entity_id

    for root_dir, _, files in os.walk(metas_dir):
        for filename in files:
            if not filename.lower().endswith(".xml"):
                continue
            path = os.path.join(root_dir, filename)
            try:
                root = meta_xml_root(path)
            except ET.ParseError:
                continue
            for node in root.iter():
                node_id = meta_node_id(node)
                if not node_id:
                    continue
                entity_id = aliases.get(node_id) or aliases.get(node_id.lower())
                if not entity_id:
                    continue
                node_values = meta_node_properties(node)
                if node_values:
                    result.setdefault(entity_id, {}).update(node_values)
    return {entity_id: add_case_aliases(values) for entity_id, values in result.items()}


def convert():
    entities_root = parse("entities.xml")
    almanac_root = parse("almanac.xml")
    tag_definitions = load_tag_definitions(almanac_root)
    enums = load_enums(almanac_root)
    all_entities = load_entities(entities_root, load_templates(entities_root))
    almanac = load_almanac(almanac_root)
    enemy_root = ET.fromstring(ET.tostring(almanac_root, encoding="unicode"))
    contraptions_section = enemy_root.find("contraptions")
    enemies_section = enemy_root.find("enemies")
    if contraptions_section is not None:
        contraptions_section.tag = "_contraptions"
    if enemies_section is not None:
        enemies_section.tag = "contraptions"
        for entry_id, entry in load_almanac(enemy_root).items():
            entity = all_entities.get(entry_id)
            if entity and entity.get("type") == "2" and entity.get("name"):
                entry["type"] = "enemy"
                almanac[entry_id] = entry
    meta_properties = load_meta_entity_properties(all_entities)
    armor_health = load_armor_health()
    globals_raw = variable_map(almanac_root.find("globalVariables"))
    globals_raw.update({
        "armor_hp": 'property("mvz2:armor_hp")',
        "mvz2:armor_hp": 'property("mvz2:armor_hp")',
        "helmet_hp": 'property("mvz2:armor_hp")',
        "mvz2:helmet_hp": 'property("mvz2:armor_hp")',
        "shield_hp": 'property("mvz2:shield_hp")',
        "mvz2:shield_hp": 'property("mvz2:shield_hp")',
    })

    ids = list(almanac)
    ids.extend(
        entry_id for entry_id, entity in all_entities.items()
        if entity.get("type") == "1" and entry_id not in almanac
    )
    merged = {}
    for entry_id in ids:
        book = almanac.get(entry_id, {
            "id": entry_id,
            "header": [],
            "properties": [],
            "flavor": [],
            "variables": {},
            "sourceTags": [],
        })
        entity = all_entities.get(entry_id, {})
        base_values = {**entity.get("properties", {}), **meta_properties.get(entry_id, {})}
        values = add_case_aliases({**base_values, **armor_properties(base_values, armor_health)})
        merged[entry_id] = {
            **book,
            "name": entity.get("name", entry_id),
            "entityProperties": values,
            "cost": "" if book.get("type") == "enemy" else values.get("mvz2:cost", ""),
            "rechargeId": "" if book.get("type") == "enemy" else values.get("mvz2:rechargeId", ""),
        }

    lookup = {
        key: {
            **entry,
            "entityProperties": add_case_aliases({
                **entry.get("properties", {}),
                **meta_properties.get(key, {}),
                **armor_properties({**entry.get("properties", {}), **meta_properties.get(key, {})}, armor_health),
            }),
        }
        for key, entry in all_entities.items()
    }
    lookup.update(merged)
    resolver = Resolver(lookup, globals_raw)
    entity_names = {
        alias: entity.get("name", entity_id)
        for entity_id, entity in all_entities.items()
        for alias in (entity_id, entity_id.lower())
    }
    output = []
    for entry_id, item in merged.items():
        global_values = {name: resolver.global_value(entry_id, name) for name in globals_raw}
        local_values = {name: resolver.local(entry_id, name) for name in item.get("variables", {})}
        for field in ("header", "properties", "flavor"):
            item[field] = replace_vars(item.get(field, []), global_values, local_values)
            item[field] = [normalize_markup(value, entity_names, tag_definitions, enums) for value in item[field]]
        item["flavor"] = ["<br>".join(item.get("flavor", []))]
        record = compact(item, tag_definitions, enums)
        if item.get("type"):
            record["type"] = item["type"]
        output.append(record)

    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    print(convert())