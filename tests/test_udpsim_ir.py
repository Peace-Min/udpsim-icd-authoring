"""Synthetic IR tests; run: python -m unittest discover -s tests -p test_udpsim_ir.py."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/udpsim-icd-authoring/scripts/icd_tool.py"
spec = importlib.util.spec_from_file_location("icd_tool", TOOL)
icd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(icd)
FIXTURE = ROOT / "tests/fixtures/udpsim-ir/synthetic.json"


class IrTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def reject(self, code):
        errors = icd.validate_ir(self.data)
        self.assertTrue(errors)
        self.assertIn(code, [error["code"] for error in errors], errors)
        self.assertTrue(all(error["path"].startswith("$") for error in errors))

    def test_nested_valid(self):
        self.assertEqual([], icd.validate_ir(self.data))
        root = ET.fromstring(icd.xml_bytes(self.data))
        self.assertEqual("little", root.attrib["endian"])
        self.assertEqual("2", root.find("Send/Message/Field").attrib["count"])
        self.assertEqual("13", root.find("Receive/Message").attrib["length"])

    def test_big_endian_valid(self):
        self.data["endian"] = "big"
        self.assertEqual([], icd.validate_ir(self.data))

    def test_minimal_header_only(self):
        self.data["messages"][0]["fields"] = []
        self.data["messages"][0]["length"] = 7
        self.assertEqual([], icd.validate_ir(self.data))

    def test_missing_endian(self):
        del self.data["endian"]
        self.reject("required")

    def test_unknown_property(self):
        self.data["messages"][0]["offset"] = 0
        self.reject("unknown_property")

    def test_wrong_endian(self):
        self.data["endian"] = "native"
        self.reject("choice")

    def test_empty_evidence(self):
        self.data["evidence"] = []
        self.reject("array_empty")

    def test_missing_evidence_locator(self):
        self.data["evidence"] = [{"source": "synthetic.txt"}]
        self.reject("required")

    def test_optional_field_evidence(self):
        self.data["types"][0]["fields"][0]["evidence"] = [{"source": "synthetic.txt", "locator": "line 3"}]
        self.assertEqual([], icd.validate_ir(self.data))

    def test_enum_alias_values(self):
        self.data["enums"][0]["items"].append({"name": "AlsoOn", "value": 1})
        self.assertEqual([], icd.validate_ir(self.data))

    def test_invalid_xml_unicode(self):
        self.data["name"] = "Invalid\ufffe"
        self.reject("xml_character")

    def test_scalar_wrong_shape(self):
        for invalid in (None, [], "text", 1):
            self.assertTrue(icd.validate_ir(invalid))

    def test_count_one_retains_array(self):
        for message in self.data["messages"]:
            message["fields"][0]["count"] = 1
            message["length"] = 10
        self.assertEqual([], icd.validate_ir(self.data))
        root = ET.fromstring(icd.xml_bytes(self.data))
        self.assertEqual("1", root.find("Send/Message/Field").attrib["count"])

    def test_unresolved_blocks(self):
        self.data["unresolved"] = ["Byte order missing in original"]
        self.reject("unresolved_facts")

    def test_bool_float_string_numbers(self):
        for invalid in (True, 13.0, "13", "0x0d", None):
            with self.subTest(value=invalid):
                self.data["messages"][0]["length"] = invalid
                self.reject("integer_range")

    def test_negative_id(self):
        self.data["messages"][0]["id"] = -1
        self.reject("integer_range")

    def test_uint32_overflow(self):
        self.data["messages"][0]["id"] = 4294967296
        self.reject("integer_range")

    def test_duplicate_send_receive_id(self):
        self.data["messages"][1]["id"] = self.data["messages"][0]["id"]
        self.reject("duplicate")

    def test_duplicate_code(self):
        self.data["messages"][1]["code"] = self.data["messages"][0]["code"]
        self.reject("duplicate")

    def test_duplicate_header_body_name(self):
        self.data["messages"][0]["fields"][0]["name"] = "Id"
        self.reject("duplicate")

    def test_duplicate_type(self):
        self.data["types"].append(copy.deepcopy(self.data["types"][0]))
        self.reject("duplicate")

    def test_duplicate_enum_item(self):
        self.data["enums"][0]["items"][1]["name"] = "Off"
        self.reject("duplicate")

    def test_unsupported_float_type(self):
        self.data["types"][0]["fields"][0]["type"] = "float32"
        self.reject("unknown_type")

    def test_primitive_type_shadow(self):
        self.data["types"][0]["name"] = "uint8"
        self.reject("duplicate")

    def test_invalid_identifier(self):
        self.data["types"][0]["fields"][0]["name"] = "Array[0]"
        self.reject("identifier")

    def test_header_cannot_array(self):
        self.data["header"][0]["count"] = 2
        self.reject("unknown_property")

    def test_body_cannot_role(self):
        self.data["types"][0]["fields"][0]["role"] = "id"
        self.reject("unknown_property")

    def test_header_roles_required(self):
        del self.data["header"][0]["role"]
        self.reject("header_role")

    def test_max_seq_only(self):
        self.data["header"][0]["max"] = 10
        self.reject("seq_only")

    def test_max_header_width(self):
        self.data["header"][2]["max"] = 65536
        self.reject("header_width")

    def test_message_length_mismatch(self):
        self.data["messages"][0]["length"] = 12
        self.reject("length_mismatch")

    def test_id_header_capacity(self):
        self.data["messages"][0]["id"] = 65536
        self.reject("header_capacity")

    def test_length_header_capacity(self):
        self.data["header"][1]["type"] = "uint8"
        for message in self.data["messages"]:
            message["fields"] = [{"name": "Payload", "type": "uint8", "count": 250}]
            message["length"] = 256
        self.reject("header_capacity")

    def test_bits_overlap(self):
        self.data["types"][0]["fields"][1]["bits"][1]["from"] = 0
        self.reject("bit_overlap")

    def test_bits_reverse(self):
        self.data["types"][0]["fields"][1]["bits"][1]["from"] = 3
        self.reject("bit_range")

    def test_bits_type_width(self):
        self.data["types"][0]["fields"][1]["bits"][1]["to"] = 8
        self.reject("bit_range")

    def test_enum_width(self):
        self.data["enums"][0]["items"][1]["value"] = 2
        self.reject("enum_width")

    def test_unknown_enum(self):
        self.data["types"][0]["fields"][1]["bits"][0]["enum"] = "Unknown"
        self.reject("unknown_enum")

    def test_enum_field_with_bits_rejected(self):
        self.data["types"][0]["fields"][1]["enum"] = "ReadyState"
        self.reject("enum_with_bits")

    def test_struct_with_bits(self):
        self.data["messages"][0]["fields"][0]["enum"] = "ReadyState"
        self.reject("struct_annotations")

    def test_array_zero_and_overflow(self):
        for invalid in (0, 65508):
            self.data["messages"][0]["fields"][0]["count"] = invalid
            self.reject("integer_range")

    def test_array_expansion_bounded(self):
        self.data["messages"][0]["fields"][0]["count"] = 65507
        self.reject("expansion_limit")

    def test_maximum_udp_length(self):
        self.data["header"] = self.data["header"][:2]
        self.data["messages"] = self.data["messages"][:1]
        self.data["messages"][0]["fields"] = [{"name": "Payload", "type": "uint8", "count": 65503}]
        self.data["messages"][0]["length"] = 65507
        self.assertEqual([], icd.validate_ir(self.data))

    def test_cycle_unused_type(self):
        self.data["types"].append({"name": "Recursive", "fields": [{"name": "Self", "type": "Recursive"}]})
        self.reject("cycle")

    def test_depth_limit(self):
        self.data["types"] += [{"name": f"S{i}", "fields": [{"name": "Inner", "type": f"S{i+1}" if i < 33 else "uint8"}]} for i in range(34)]
        self.reject("depth_limit")

    def test_maximum_struct_depth(self):
        self.data["types"] = [{"name": f"S{i}", "fields": [{"name": "Inner", "type": f"S{i+1}" if i < 31 else "uint8"}]} for i in range(32)]
        for message in self.data["messages"]:
            message["fields"] = [{"name": "Root", "type": "S0"}]
            message["length"] = 8
        self.assertEqual([], icd.validate_ir(self.data))

    def test_xml_escaping_and_format(self):
        raw = icd.xml_bytes(self.data)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"&amp;", raw)
        self.assertIn(b"\r\n", raw)
        self.assertEqual("Synthetic ICD & array example", ET.fromstring(raw).attrib["name"])

    def test_convert_cli_atomic_and_failure_preserves_previous(self):
        with tempfile.TemporaryDirectory(prefix="icd QA ") as folder:
            path = Path(folder)
            source, output = path / "input.json", path / "output.xml"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "convert", "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)
            self.assertEqual("NOT_RUN", json.loads(run.stdout)["xml_core_validation"])
            accepted = output.read_bytes()
            self.data["messages"][0]["length"] = 999
            source.write_text(json.dumps(self.data), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "convert", "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(0, run.returncode)
            self.assertEqual("IR_FAIL", json.loads(run.stdout)["status"])
            self.assertEqual(accepted, output.read_bytes())

    def test_duplicate_json_property(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "duplicate.json"
            source.write_text('{"name":"first","name":"second"}', encoding="utf-8")
            with self.assertRaises(icd.InvalidJson):
                icd.load_ir(source)

    def test_missing_file_cli(self):
        run = subprocess.run([sys.executable, str(TOOL), "validate", "--input", "__does_not_exist__.json"], capture_output=True, text=True)
        self.assertNotEqual(0, run.returncode)
        self.assertEqual("IR_FAIL", json.loads(run.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
