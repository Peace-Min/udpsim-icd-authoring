#!/usr/bin/env python3
"""Validate traceable ICD IR v1 and generate UdpSim XML, using only stdlib."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

PRIMITIVES = {"uint8": 1, "uint16": 2, "uint32": 4, "int8": 1, "int16": 2, "int32": 4}
LIMIT = 65507
UINT32 = 4294967295


class InvalidJson(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidJson("Duplicate JSON property: " + key)
        result[key] = value
    return result


def load_ir(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=unique_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(InvalidJson("Invalid number: " + value)))


class Validator:
    def __init__(self):
        self.errors = []

    def error(self, path, code, expected, observed, clarification=False):
        self.errors.append({"path": path, "code": code, "expected": expected,
                            "observed": observed, "action": "clarify" if clarification else "correct_from_source"})

    def obj(self, value, path, required, optional=()):
        if not isinstance(value, dict):
            self.error(path, "object_required", "object", type(value).__name__)
            return False
        for key in sorted(set(required) - value.keys()):
            self.error(path + "." + key, "required", "present", "missing")
        for key in sorted(value.keys() - set(required) - set(optional)):
            self.error(path + "." + key, "unknown_property", "documented property", key)
        return True

    def array(self, value, path, minimum=0):
        if not isinstance(value, list):
            self.error(path, "array_required", "array", type(value).__name__)
            return []
        if len(value) < minimum:
            self.error(path, "array_empty", "at least " + str(minimum) + " item(s)", len(value))
        return value

    def text(self, value, path, identifier=False):
        if not isinstance(value, str) or not value.strip():
            self.error(path, "text_required", "nonempty string", value)
            return
        if any(not (char in "\t\r\n" or 0x20 <= ord(char) <= 0xD7FF or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF) for char in value):
            self.error(path, "xml_character", "XML-compatible text", "invalid character")
        if identifier and (value != value.strip() or any(char in value for char in ".[]")):
            self.error(path, "identifier", "no surrounding whitespace or . [ ]", value)

    def integer(self, value, path, minimum=0, maximum=UINT32):
        if type(value) is not int or not minimum <= value <= maximum:
            self.error(path, "integer_range", f"JSON integer {minimum}..{maximum}", value)

    def choice(self, value, path, choices):
        if value not in choices or not isinstance(value, str):
            self.error(path, "choice", list(choices), value)

    def evidence(self, value, path):
        for index, entry in enumerate(self.array(value, path, 1)):
            at = f"{path}[{index}]"
            if self.obj(entry, at, ("source", "locator")):
                self.text(entry.get("source"), at + ".source")
                self.text(entry.get("locator"), at + ".locator")

    def field_shape(self, field, path, header=False):
        optional = ("role", "max", "scope", "response", "evidence") if header else ("count", "enum", "bits", "evidence")
        if not self.obj(field, path, ("name", "type"), optional):
            return
        self.text(field.get("name"), path + ".name", True)
        self.text(field.get("type"), path + ".type", True)
        if "evidence" in field:
            self.evidence(field["evidence"], path + ".evidence")
        if header:
            if "role" in field:
                self.choice(field["role"], path + ".role", ("id", "length", "seq"))
            if "max" in field:
                self.integer(field["max"], path + ".max")
            if "scope" in field:
                self.choice(field["scope"], path + ".scope", ("link", "message"))
            if "response" in field:
                self.choice(field["response"], path + ".response", ("count", "echo"))
            return
        if "count" in field:
            self.integer(field["count"], path + ".count", 1, LIMIT)
        if "enum" in field:
            self.text(field["enum"], path + ".enum", True)
        if "bits" in field:
            for index, bits in enumerate(self.array(field["bits"], path + ".bits", 1)):
                at = f"{path}.bits[{index}]"
                if self.obj(bits, at, ("name", "from", "to"), ("enum", "evidence")):
                    self.text(bits.get("name"), at + ".name", True)
                    self.integer(bits.get("from"), at + ".from", 0, 31)
                    self.integer(bits.get("to"), at + ".to", 0, 31)
                    if "enum" in bits:
                        self.text(bits["enum"], at + ".enum", True)
                    if "evidence" in bits:
                        self.evidence(bits["evidence"], at + ".evidence")

    def shape(self, data):
        required = ("schema_version", "name", "endian", "evidence", "unresolved", "enums", "types", "header", "messages")
        if not self.obj(data, "$", required):
            return
        self.integer(data.get("schema_version"), "$.schema_version", 1, 1)
        self.text(data.get("name"), "$.name")
        self.choice(data.get("endian"), "$.endian", ("big", "little"))
        self.evidence(data.get("evidence"), "$.evidence")
        unresolved = self.array(data.get("unresolved"), "$.unresolved")
        if unresolved:
            self.error("$.unresolved", "unresolved_facts", "empty before conversion", unresolved, True)
        for index, enum in enumerate(self.array(data.get("enums"), "$.enums")):
            at = f"$.enums[{index}]"
            if not self.obj(enum, at, ("name", "items")):
                continue
            self.text(enum.get("name"), at + ".name", True)
            for item_index, item in enumerate(self.array(enum.get("items"), at + ".items")):
                item_at = f"{at}.items[{item_index}]"
                if self.obj(item, item_at, ("name", "value")):
                    self.text(item.get("name"), item_at + ".name")
                    self.integer(item.get("value"), item_at + ".value")
        for index, struct in enumerate(self.array(data.get("types"), "$.types")):
            at = f"$.types[{index}]"
            if self.obj(struct, at, ("name", "fields")):
                self.text(struct.get("name"), at + ".name", True)
                for field_index, field in enumerate(self.array(struct.get("fields"), at + ".fields", 1)):
                    self.field_shape(field, f"{at}.fields[{field_index}]")
        for index, field in enumerate(self.array(data.get("header"), "$.header", 1)):
            self.field_shape(field, f"$.header[{index}]", True)
        for index, message in enumerate(self.array(data.get("messages"), "$.messages", 1)):
            at = f"$.messages[{index}]"
            if not self.obj(message, at, ("direction", "code", "id", "name", "length", "fields"), ("evidence",)):
                continue
            self.choice(message.get("direction"), at + ".direction", ("send", "receive"))
            self.text(message.get("code"), at + ".code")
            self.text(message.get("name"), at + ".name")
            self.integer(message.get("id"), at + ".id")
            self.integer(message.get("length"), at + ".length", 1, LIMIT)
            if "evidence" in message:
                self.evidence(message["evidence"], at + ".evidence")
            for field_index, field in enumerate(self.array(message.get("fields"), at + ".fields")):
                self.field_shape(field, f"{at}.fields[{field_index}]")

    def unique(self, entries, key, path, forbidden=()):
        seen = set(forbidden)
        for index, entry in enumerate(entries):
            value = entry[key]
            if value in seen:
                self.error(f"{path}[{index}].{key}", "duplicate", "unique " + key, value)
            seen.add(value)

    def semantic(self, data):
        enums = {entry["name"]: entry for entry in data["enums"]}
        structs = {entry["name"]: entry for entry in data["types"]}
        self.unique(data["enums"], "name", "$.enums")
        self.unique(data["types"], "name", "$.types", PRIMITIVES)
        self.unique(data["header"], "name", "$.header")
        self.unique(data["messages"], "code", "$.messages")
        self.unique(data["messages"], "id", "$.messages")
        for index, enum in enumerate(data["enums"]):
            self.unique(enum["items"], "name", f"$.enums[{index}].items")

        def check_enum(name, width, path):
            if name not in enums:
                self.error(path, "unknown_enum", "declared enum name", name)
            elif any(item["value"] >= (1 << width) for item in enums[name]["items"]):
                self.error(path, "enum_width", f"all values < 2^{width}", name)

        def fields(entries, path, header=False):
            for index, field in enumerate(entries):
                at = f"{path}[{index}]"
                primitive = field["type"] in PRIMITIVES
                if not primitive and (header or field["type"] not in structs):
                    self.error(at + ".type", "unknown_type", "primitive" if header else "primitive or declared struct", field["type"])
                    continue
                if not primitive:
                    if "enum" in field or "bits" in field:
                        self.error(at, "struct_annotations", "no enum/bits on struct", field["type"])
                    continue
                width = PRIMITIVES[field["type"]] * 8
                if header:
                    if any(key in field for key in ("max", "scope", "response")) and field.get("role") != "seq":
                        self.error(at, "seq_only", "max/scope/response only on seq", field.get("role"))
                    if field.get("max", 0) >= (1 << width):
                        self.error(at + ".max", "header_width", f"< 2^{width}", field["max"])
                    continue
                if "enum" in field:
                    check_enum(field["enum"], width, at + ".enum")
                    if "bits" in field:
                        self.error(at, "enum_with_bits", "enum on individual Bits only", field["enum"])
                self.unique(field.get("bits", []), "name", at + ".bits")
                mask = 0
                for bit_index, bits in enumerate(field.get("bits", [])):
                    bit_at = f"{at}.bits[{bit_index}]"
                    if not 0 <= bits["from"] <= bits["to"] < width:
                        self.error(bit_at, "bit_range", f"0 <= from <= to < {width}", [bits["from"], bits["to"]])
                        continue
                    bit_width = bits["to"] - bits["from"] + 1
                    current = ((1 << bit_width) - 1) << bits["from"]
                    if mask & current:
                        self.error(bit_at, "bit_overlap", "nonoverlapping ranges", [bits["from"], bits["to"]])
                    mask |= current
                    if "enum" in bits:
                        check_enum(bits["enum"], bit_width, bit_at + ".enum")

        fields(data["header"], "$.header", True)
        for index, struct in enumerate(data["types"]):
            at = f"$.types[{index}].fields"
            self.unique(struct["fields"], "name", at)
            fields(struct["fields"], at)
        header_names = [field["name"] for field in data["header"]]
        for index, message in enumerate(data["messages"]):
            at = f"$.messages[{index}].fields"
            self.unique(message["fields"], "name", at, header_names)
            fields(message["fields"], at)
        roles = {}
        for role in ("id", "length", "seq"):
            matched = [field for field in data["header"] if field.get("role") == role]
            if len(matched) != 1 and (role != "seq" or len(matched) > 1):
                self.error("$.header", "header_role", f"{'at most' if role == 'seq' else 'exactly'} one {role}", len(matched))
            if len(matched) == 1:
                roles[role] = matched[0]
        if self.errors:
            return

        def measure(entries, path, ancestors=(), depth=0):
            size = expanded = 0
            for index, field in enumerate(entries):
                at = f"{path}[{index}]"
                level = depth + (1 if "count" in field else 0)
                if level > 32:
                    self.error(at, "depth_limit", "expanded depth <= 32", level)
                    return 0, 0
                if field["type"] in PRIMITIVES:
                    child_size, child_count = PRIMITIVES[field["type"]], 1
                else:
                    name = field["type"]
                    if name in ancestors:
                        self.error(at + ".type", "cycle", "acyclic struct references", name)
                        return 0, 0
                    child_size, child_count = measure(structs[name]["fields"], at + ".members", ancestors + (name,), level + 1)
                count = field.get("count", 1)
                size += child_size * count
                expanded += child_count * count
                if size > LIMIT or expanded > LIMIT:
                    self.error(at, "expansion_limit", "bytes and expanded primitive fields <= 65507", {"bytes": size, "fields": expanded})
                    return size, expanded
            return size, expanded

        for index, struct in enumerate(data["types"]):
            measure(struct["fields"], f"$.types[{index}].fields", (struct["name"],), 1)
        header_size = sum(PRIMITIVES[field["type"]] for field in data["header"])
        for index, message in enumerate(data["messages"]):
            at = f"$.messages[{index}]"
            size, _ = measure(message["fields"], at + ".fields")
            computed = header_size + size
            if computed != message["length"]:
                self.error(at + ".length", "length_mismatch", computed, message["length"])
            if computed > LIMIT:
                self.error(at + ".length", "udp_limit", "<= 65507", computed)
            for role, value in (("id", message["id"]), ("length", computed)):
                capacity = (1 << (8 * PRIMITIVES[roles[role]["type"]])) - 1
                if value > capacity:
                    self.error(at + "." + role, "header_capacity", f"<= {capacity}", value)

    def validate(self, data):
        self.shape(data)
        if not self.errors:
            self.semantic(data)
        return self.errors


def validate_ir(data):
    return Validator().validate(data)


def xml_bytes(data):
    root = ET.Element("Icd", {"name": data["name"], "endian": data["endian"]})

    def add_fields(parent, fields):
        for field in fields:
            attrs = {key: str(field[key]) for key in ("name", "type", "role", "max", "scope", "response", "count", "enum") if key in field}
            element = ET.SubElement(parent, "Field", attrs)
            for bits in field.get("bits", []):
                ET.SubElement(element, "Bits", {key: str(bits[key]) for key in ("name", "from", "to", "enum") if key in bits})

    if data["enums"]:
        group = ET.SubElement(root, "Enums")
        for enum in data["enums"]:
            element = ET.SubElement(group, "Enum", {"name": enum["name"]})
            for item in enum["items"]:
                ET.SubElement(element, "Item", {"name": item["name"], "value": str(item["value"])})
    if data["types"]:
        group = ET.SubElement(root, "Types")
        for struct in data["types"]:
            add_fields(ET.SubElement(group, "Struct", {"name": struct["name"]}), struct["fields"])
    add_fields(ET.SubElement(root, "Header"), data["header"])
    for direction, tag in (("send", "Send"), ("receive", "Receive")):
        messages = [message for message in data["messages"] if message["direction"] == direction]
        if messages:
            group = ET.SubElement(root, tag)
            for message in messages:
                element = ET.SubElement(group, "Message", {key: str(message[key]) for key in ("code", "id", "name", "length")})
                add_fields(element, message["fields"])
    ET.indent(root, space="  ")
    return b"\xef\xbb\xbf" + (ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n").replace("\n", "\r\n").encode("utf-8")


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".icd-", delete=False) as stream:
            name = stream.name
            stream.write(content)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "convert"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "convert" and not args.output:
            raise ValueError("convert requires --output XML")
        if args.command == "convert" and Path(args.input).resolve() == Path(args.output).resolve():
            raise ValueError("Input and XML output must be different files")
        data = load_ir(args.input)
        errors = validate_ir(data)
        if errors:
            print(json.dumps({"status": "IR_FAIL", "errors": errors}, ensure_ascii=True))
            return 1
        if args.command == "convert":
            atomic_write(args.output, xml_bytes(data))
        print(json.dumps({"status": "IR_PASS", "xml_generated": args.command == "convert",
                          "xml_core_validation": "NOT_RUN", "messages": len(data["messages"])}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, RecursionError) as error:
        print(json.dumps({"status": "IR_FAIL", "errors": [{"path": "$", "code": "input_or_io",
                          "expected": "readable strict JSON and writable distinct XML output", "observed": str(error),
                          "action": "correct_from_source"}]}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
