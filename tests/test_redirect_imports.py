import json
from pathlib import Path
import struct
import tempfile
import unittest

from redirect_imports import IMPORT_RECORD, RedirectError, redirect_imports


class RedirectImportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / "input.u"
        self.manifest = self.root / "input.manifest.json"
        self.output = self.root / "output.u"

        names = [
            "Core",
            "Package",
            "Engine",
            "Material",
            "MissingAssets",
            "ExistingAssets",
            "MissingMaterial",
            "ExistingMaterial",
        ]
        records = [
            (0, 0, 1, 0, 0, 4, 0),
            (0, 0, 1, 0, 0, 5, 0),
            (2, 0, 3, 0, -1, 6, 0),
            (2, 0, 3, 0, -2, 7, 0),
        ]
        prefix = bytes(range(32))
        self.original = prefix + b"".join(IMPORT_RECORD.pack(*record) for record in records)
        self.package.write_bytes(self.original)
        imports = [
            {
                "index": 0,
                "package_index": -1,
                "class_package": "Core",
                "class_name": "Package",
                "outer_index": 0,
                "object_name": "MissingAssets",
                "object_path": "MissingAssets",
            },
            {
                "index": 1,
                "package_index": -2,
                "class_package": "Core",
                "class_name": "Package",
                "outer_index": 0,
                "object_name": "ExistingAssets",
                "object_path": "ExistingAssets",
            },
            {
                "index": 2,
                "package_index": -3,
                "class_package": "Engine",
                "class_name": "Material",
                "outer_index": -1,
                "object_name": "MissingMaterial",
                "object_path": "MissingAssets.MissingMaterial",
            },
            {
                "index": 3,
                "package_index": -4,
                "class_package": "Engine",
                "class_name": "Material",
                "outer_index": -2,
                "object_name": "ExistingMaterial",
                "object_path": "ExistingAssets.ExistingMaterial",
            },
        ]
        imports_end = len(self.original)
        document = {
            "byte_order": "little",
            "layout_validation": {
                "imports_end": imports_end,
                "expected_imports_end": imports_end,
            },
            "names": [
                {"index": index, "name": name, "flags": "0x0"}
                for index, name in enumerate(names)
            ],
            "imports": imports,
        }
        self.manifest.write_text(json.dumps(document), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_redirect_copies_only_the_target_record(self):
        report = redirect_imports(
            self.manifest,
            self.package,
            self.output,
            [("MissingAssets.MissingMaterial", "ExistingAssets.ExistingMaterial")],
        )
        self.assertEqual(
            report,
            [(2, "MissingAssets.MissingMaterial", 3, "ExistingAssets.ExistingMaterial")],
        )
        result = self.output.read_bytes()
        start = 32
        source = start + 2 * IMPORT_RECORD.size
        target = start + 3 * IMPORT_RECORD.size
        self.assertEqual(result[source : source + IMPORT_RECORD.size], self.original[target:])
        self.assertEqual(result[:source], self.original[:source])
        self.assertEqual(result[source + IMPORT_RECORD.size :], self.original[source + IMPORT_RECORD.size :])

    def test_refuses_to_overwrite_output(self):
        self.output.write_bytes(b"keep")
        with self.assertRaisesRegex(RedirectError, "output already exists"):
            redirect_imports(
                self.manifest,
                self.package,
                self.output,
                [("MissingAssets.MissingMaterial", "ExistingAssets.ExistingMaterial")],
            )
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_rejects_package_manifest_mismatch(self):
        damaged = bytearray(self.original)
        struct.pack_into("<i", damaged, 32 + 2 * IMPORT_RECORD.size, 7)
        self.package.write_bytes(damaged)
        with self.assertRaisesRegex(RedirectError, "does not match manifest"):
            redirect_imports(
                self.manifest,
                self.package,
                self.output,
                [("MissingAssets.MissingMaterial", "ExistingAssets.ExistingMaterial")],
            )

    def test_rejects_incompatible_import_classes(self):
        with self.assertRaisesRegex(RedirectError, "incompatible import classes"):
            redirect_imports(
                self.manifest,
                self.package,
                self.output,
                [("MissingAssets.MissingMaterial", "ExistingAssets")],
            )


if __name__ == "__main__":
    unittest.main()
