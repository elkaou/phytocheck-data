#!/usr/bin/env python3
"""Collecte les autorisations d'urgence Article 53 publiées par le ministère.

Le ministère publie les décisions actives sous forme de listes HTML accompagnées
par de décisions PDF. Ce script extrait les champs structurés, conserve les
décisions historiques déjà collectées (pour signaler les expirations côté app)
et met à jour le manifest consommé par PhytoCheck.

Aucune condition détaillée des PDF n'est interprétée : le PDF officiel est
conservé comme référence juridiquement opposable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCE_URL = (
    "https://agriculture.gouv.fr/produits-phytopharmaceutiques-"
    "autorisations-de-mise-sur-le-marche-dune-duree-maximale-de-120-jours"
)
USER_AGENT = "PhytoCheck-Article53-Collector/1.0 (+https://phytocheck.com)"
AMM_PATTERN = re.compile(r"^\d{7}$")


class MinistryAuthorizationParser(HTMLParser):
    """Extrait les listes Article 53 et le lien PDF qui leur succède."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self._in_list = False
        self._list_depth = 0
        self._in_item = False
        self._item_parts: list[str] = []
        self._current_fields: dict[str, str] = {}
        self._awaiting_pdf: dict[str, str] | None = None
        self._in_download_link = False
        self._download_href = ""
        self._download_text: list[str] = []
        self.records: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "ul":
            if not self._in_list:
                self._in_list = True
                self._current_fields = {}
            self._list_depth += 1
            return

        if tag == "li" and self._in_list and self._list_depth == 1:
            self._in_item = True
            self._item_parts = []
            return

        if tag == "a" and self._awaiting_pdf is not None:
            href = attributes.get("href") or ""
            if "/telecharger/" in href:
                self._in_download_link = True
                self._download_href = urljoin(self.source_url, href)
                self._download_text = []

    def handle_data(self, data: str) -> None:
        if self._in_item:
            self._item_parts.append(data)
        if self._in_download_link:
            self._download_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self._in_item:
            text = " ".join("".join(self._item_parts).split())
            if " : " in text:
                key, value = text.split(" : ", 1)
                self._current_fields[key.strip()] = value.strip()
            self._in_item = False
            self._item_parts = []
            return

        if tag == "ul" and self._in_list:
            self._list_depth -= 1
            if self._list_depth == 0:
                amm = self._current_fields.get("Numéro d'AMM", "")
                if AMM_PATTERN.fullmatch(amm):
                    self._awaiting_pdf = dict(self._current_fields)
                self._in_list = False
                self._current_fields = {}
            return

        if tag == "a" and self._in_download_link:
            text = " ".join("".join(self._download_text).split())
            amm = self._awaiting_pdf.get("Numéro d'AMM", "") if self._awaiting_pdf else ""
            if self._awaiting_pdf and amm and amm in text:
                self._awaiting_pdf["decisionPdfUrl"] = self._download_href
                self.records.append(self._awaiting_pdf)
                self._awaiting_pdf = None
            self._in_download_link = False
            self._download_href = ""
            self._download_text = []


def to_iso_date(value: str) -> str:
    """Convertit une date ministérielle JJ/MM/AAAA en AAAA-MM-JJ."""
    return datetime.strptime(value.strip(), "%d/%m/%Y").date().isoformat()


def stable_id(record: dict[str, str]) -> str:
    """Construit un identifiant stable au niveau de la décision, pas de l'AMM."""
    fingerprint = "|".join(
        record.get(key, "")
        for key in ("amm", "issuedAt", "expiresAt", "cultures", "purpose", "decisionPdfUrl")
    )
    return f"article53-{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:20]}"


def normalize_record(fields: dict[str, str], source_url: str, retrieved_at: str) -> dict[str, str]:
    """Normalise une décision HTML dans le contrat public de PhytoCheck."""
    amm = fields.get("Numéro d'AMM", "").strip()
    if not AMM_PATTERN.fullmatch(amm):
        raise ValueError(f"Numéro d'AMM invalide : {amm!r}")

    record = {
        "amm": amm,
        "productName": fields.get("Produit phytopharmaceutique (PPP)", "").strip(),
        "cultures": fields.get("Culture(s) concernée(s)", "").strip(),
        "purpose": fields.get("Organisme nuisible / effet recherché", "").strip(),
        "activeSubstances": fields.get("Substance active", "").strip(),
        "issuedAt": to_iso_date(fields.get("Date de délivrance", "")),
        "expiresAt": to_iso_date(fields.get("Échéance", "")),
        "decisionPdfUrl": fields.get("decisionPdfUrl", "").strip(),
        "sourcePageUrl": source_url,
        "sourceRetrievedAt": retrieved_at,
    }
    if not record["productName"] or not record["cultures"] or not record["decisionPdfUrl"]:
        raise ValueError(f"Décision Article 53 incomplète pour l'AMM {amm}")
    record["id"] = stable_id(record)
    return record


def parse_authorizations(html: str, source_url: str, retrieved_at: str) -> list[dict[str, str]]:
    parser = MinistryAuthorizationParser(source_url)
    parser.feed(html)
    parser.close()

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for fields in parser.records:
        record = normalize_record(fields, source_url, retrieved_at)
        if record["id"] not in seen:
            records.append(record)
            seen.add(record["id"])
    return records


def fetch_html(source_url: str) -> str:
    request = Request(source_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Réponse HTTP inattendue : {response.status}")
        return response.read().decode("utf-8", errors="replace")


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def normalize_for_comparison(record: dict[str, Any]) -> dict[str, Any]:
    """Ignore l'horodatage de collecte afin d'éviter des mises à jour inutiles."""
    return {key: value for key, value in record.items() if key != "sourceRetrievedAt"}


def update_data(
    output_path: Path,
    manifest_path: Path,
    source_url: str,
    html: str,
    retrieved_at: str,
) -> tuple[bool, int, int]:
    """Fusionne les décisions actuelles avec l'historique et met à jour le manifeste."""
    fresh = parse_authorizations(html, source_url, retrieved_at)
    existing = read_json(output_path, [])
    if not isinstance(existing, list):
        raise RuntimeError(f"Le fichier existant {output_path} doit contenir une liste JSON")

    existing_by_id = {
        record.get("id"): record
        for record in existing
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }
    fresh_by_id = {record["id"]: record for record in fresh}
    merged_by_id = dict(existing_by_id)
    changed = False

    for record_id, fresh_record in fresh_by_id.items():
        previous = existing_by_id.get(record_id)
        if previous and normalize_for_comparison(previous) == normalize_for_comparison(fresh_record):
            # Préserver l'horodatage du dernier changement réel.
            fresh_record["sourceRetrievedAt"] = previous.get("sourceRetrievedAt", retrieved_at)
        else:
            changed = True
        merged_by_id[record_id] = fresh_record

    merged = sorted(
        merged_by_id.values(),
        key=lambda record: (record.get("expiresAt", ""), record.get("amm", ""), record.get("id", "")),
        reverse=True,
    )

    if len(merged) != len(existing):
        changed = True
    elif [normalize_for_comparison(record) for record in merged] != [normalize_for_comparison(record) for record in existing]:
        changed = True

    if changed or not output_path.exists():
        write_json(output_path, merged)

    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Le manifest {manifest_path} doit contenir un objet JSON")

    current_info = manifest.get("emergency_authorizations")
    current_updated_at = current_info.get("updated_at") if isinstance(current_info, dict) else None
    if changed or not current_updated_at:
        manifest["emergency_authorizations"] = {
            "updated_at": retrieved_at,
            "count": len(merged),
            "active_source_count": len(fresh),
            "source_url": source_url,
        }
        write_json(manifest_path, manifest)
        changed = True

    return changed, len(fresh), len(merged)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("emergency-authorizations.json"))
    parser.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--html-file", type=Path, help="HTML local pour les tests hors ligne")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    html = args.html_file.read_text(encoding="utf-8") if args.html_file else fetch_html(args.source_url)
    changed, current_count, total_count = update_data(
        args.output,
        args.manifest,
        args.source_url,
        html,
        retrieved_at,
    )
    print(f"Décisions Article 53 extraites : {current_count}")
    print(f"Historique publié : {total_count}")
    print("Données modifiées : " + ("oui" if changed else "non"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERREUR : {error}", file=sys.stderr)
        raise SystemExit(1)
