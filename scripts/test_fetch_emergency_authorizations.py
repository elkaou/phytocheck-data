#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("fetch_emergency_authorizations.py")
spec = importlib.util.spec_from_file_location("article53_collector", SCRIPT_PATH)
collector = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(collector)

SOURCE_URL = "https://agriculture.gouv.fr/exemple"
HTML = """
<div class="node__body">
  <ul>
    <li>Culture(s) concernée(s) : orge</li>
    <li>Organisme nuisible / effet recherché : Désherbage</li>
    <li>Produit phytopharmaceutique (PPP) : AVADEX FACTOR</li>
    <li>Numéro d'AMM : 2260551</li>
    <li>Substance active : Tri-allate</li>
    <li>Date de délivrance : 23/09/2026</li>
    <li>Échéance : 21/01/2027</li>
  </ul>
  <p>Consulter l'autorisation :</p>
  <div><a href="/telecharger/156224">n°2260551 - AVADEX FACTOR <span>pdf</span></a></div>
  <ul>
    <li>Culture(s) concernée(s) : vigne</li>
    <li>Organisme nuisible / effet recherché : Pucerons</li>
    <li>Produit phytopharmaceutique (PPP) : PRODUIT TEST</li>
    <li>Numéro d'AMM : 1234567</li>
    <li>Substance active : Substance test</li>
    <li>Date de délivrance : 01/10/2026</li>
    <li>Échéance : 29/01/2027</li>
  </ul>
  <div><a href="/telecharger/999999">n°1234567 - PRODUIT TEST pdf</a></div>
</div>
"""


class Article53CollectorTests(unittest.TestCase):
    def test_extracts_normalized_decisions_and_official_pdf(self):
        records = collector.parse_authorizations(HTML, SOURCE_URL, "2026-10-02T10:00:00Z")

        self.assertEqual(len(records), 2)
        avadex = records[0]
        self.assertEqual(avadex["amm"], "2260551")
        self.assertEqual(avadex["issuedAt"], "2026-09-23")
        self.assertEqual(avadex["expiresAt"], "2027-01-21")
        self.assertEqual(avadex["decisionPdfUrl"], "https://agriculture.gouv.fr/telecharger/156224")
        self.assertTrue(avadex["id"].startswith("article53-"))

    def test_keeps_expired_history_when_the_live_page_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            output = directory / "emergency-authorizations.json"
            manifest = directory / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

            changed, current_count, total_count = collector.update_data(
                output, manifest, SOURCE_URL, HTML, "2026-10-02T10:00:00Z"
            )
            self.assertTrue(changed)
            self.assertEqual((current_count, total_count), (2, 2))

            changed, current_count, total_count = collector.update_data(
                output, manifest, SOURCE_URL, "<div></div>", "2026-10-03T10:00:00Z"
            )
            self.assertFalse(changed)
            self.assertEqual((current_count, total_count), (0, 2))
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 2)


if __name__ == "__main__":
    unittest.main()
