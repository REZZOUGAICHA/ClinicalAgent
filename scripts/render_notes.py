"""Render Synthea CSV output into readable clinical notes, one per encounter.

Each note is split into section records with the fields
doc_id, patient_id, document_type, date, section, title, content
so that answers can cite both the document (doc_id) and the section.

The renderer only rewords facts that exist in the CSVs - it never adds
clinical statements of its own, because the CSVs are the evaluation ground truth.

Usage:
    uv run python scripts/render_notes.py --preview [ENCOUNTER_ID]
    uv run python scripts/render_notes.py --all
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/synthea_raw/csv")
NOTES_DIR = Path("data/notes")

DOCUMENT_TYPES = {
    "ambulatory": "Office Visit Note",
    "wellness": "Annual Wellness Visit Note",
    "outpatient": "Outpatient Procedure Note",
    "emergency": "Emergency Department Note",
    "urgentcare": "Urgent Care Note",
    "inpatient": "Inpatient Discharge Summary",
    "snf": "Skilled Nursing Facility Note",
    "virtual": "Telehealth Visit Note",
    "hospice": "Hospice Care Note",
}

SEX = {"F": "female", "M": "male"}


def clean_name(name):
    # Synthea appends digits to names: "Jessica140" -> "Jessica"
    return re.sub(r"\d+", "", str(name)).strip()


def clean_term(term):
    # Drop the SNOMED semantic tag: "Pneumonia (disorder)" -> "Pneumonia"
    return re.sub(r"\s*\((disorder|finding|procedure|situation|regime/therapy|"
                  r"record artifact|observable entity|environment|person|"
                  r"substance|organism|product)\)$", "", str(term)).strip()


def present(value):
    return pd.notna(value) and str(value).strip() != ""


def load_tables():
    tables = {}
    for name in ["patients", "encounters", "providers", "organizations",
                 "conditions", "medications", "observations", "procedures",
                 "immunizations", "allergies", "careplans"]:
        tables[name] = pd.read_csv(RAW_DIR / f"{name}.csv", dtype=str)
    return tables


def group_by_encounter(df):
    return {enc: rows for enc, rows in df.groupby("ENCOUNTER")}


def patient_line(patient):
    name = f"{clean_name(patient.FIRST)} {clean_name(patient.LAST)}"
    sex = SEX.get(patient.GENDER, patient.GENDER)
    return name, f"{name}, {sex}, born {patient.BIRTHDATE} (patient ID {patient.Id})"


def render_sections(enc, patient, provider, org, by_enc):
    """Return a list of (section_name, text) for one encounter."""
    sections = []
    enc_id = enc.Id
    _, patient_text = patient_line(patient)

    # Visit information
    lines = [
        f"Patient: {patient_text}.",
        f"Visit date: {enc.START[:10]}.",
        f"Visit type: {clean_term(enc.DESCRIPTION)}.",
    ]
    if provider is not None:
        lines.append(f"Clinician: {clean_name(provider.NAME)} "
                     f"({provider.SPECIALITY.title()}).")
    if org is not None:
        org_name = re.sub(r"\s+", " ", org.NAME)
        lines.append(f"Facility: {org_name}, {org.CITY}, {org.STATE}.")
    sections.append(("Visit Information", "\n".join(lines)))

    # Reason for visit
    if present(enc.REASONDESCRIPTION):
        sections.append(("Reason for Visit",
                         f"Seen for {clean_term(enc.REASONDESCRIPTION)}."))

    # Assessment: conditions recorded at this encounter
    rows = by_enc["conditions"].get(enc_id)
    if rows is not None:
        lines = []
        for c in rows.itertuples():
            line = f"- {clean_term(c.DESCRIPTION)} (onset {c.START})"
            if present(c.STOP):
                line += f", resolved {c.STOP}"
            lines.append(line + ".")
        sections.append(("Assessment", "Diagnoses recorded at this visit:\n"
                         + "\n".join(lines)))

    # Allergies
    rows = by_enc["allergies"].get(enc_id)
    if rows is not None:
        lines = []
        for a in rows.itertuples():
            line = f"- {clean_term(a.DESCRIPTION)} ({a.CATEGORY} {a.TYPE})"
            if present(a.DESCRIPTION1):
                line += f"; reaction: {clean_term(a.DESCRIPTION1).lower()}"
                if present(a.SEVERITY1):
                    line += f", {a.SEVERITY1.lower()}"
            lines.append(line + ".")
        sections.append(("Allergies", "\n".join(lines)))

    # Vital signs and laboratory results
    obs = by_enc["observations"].get(enc_id)
    if obs is not None:
        for category, heading in [("vital-signs", "Vital Signs"),
                                  ("laboratory", "Laboratory Results")]:
            sub = obs[obs.CATEGORY == category]
            if sub.empty:
                continue
            lines = []
            for o in sub.itertuples():
                units = "" if not present(o.UNITS) or o.UNITS.startswith("{") \
                    else " °C" if o.UNITS == "Cel" else f" {o.UNITS}"
                lines.append(f"- {o.DESCRIPTION}: {o.VALUE}{units}")
            sections.append((heading, "\n".join(lines)))

    # Procedures
    rows = by_enc["procedures"].get(enc_id)
    if rows is not None:
        lines = []
        for p in rows.itertuples():
            line = f"- {clean_term(p.DESCRIPTION)}"
            if present(p.REASONDESCRIPTION):
                line += f", for {clean_term(p.REASONDESCRIPTION)}"
            lines.append(line + ".")
        sections.append(("Procedures", "\n".join(lines)))

    # Medications prescribed at this encounter
    rows = by_enc["medications"].get(enc_id)
    if rows is not None:
        lines = []
        for m in rows.itertuples():
            line = f"- {m.DESCRIPTION}, started {m.START[:10]}"
            if present(m.REASONDESCRIPTION):
                line += f", for {clean_term(m.REASONDESCRIPTION)}"
            if present(m.STOP):
                line += f"; stopped {m.STOP[:10]}"
            else:
                line += "; no stop date recorded"
            lines.append(line + ".")
        sections.append(("Medications", "Medications prescribed at this visit:\n"
                         + "\n".join(lines)))

    # Immunizations
    rows = by_enc["immunizations"].get(enc_id)
    if rows is not None:
        lines = [f"- {re.sub(r'\s+', ' ', i.DESCRIPTION)}." for i in rows.itertuples()]
        sections.append(("Immunizations", "\n".join(lines)))

    # Plan: care plans started at this encounter
    rows = by_enc["careplans"].get(enc_id)
    if rows is not None:
        lines = []
        for cp in rows.itertuples():
            line = f"- {clean_term(cp.DESCRIPTION)}"
            if present(cp.REASONDESCRIPTION):
                line += f" for {clean_term(cp.REASONDESCRIPTION)}"
            line += f", started {cp.START}"
            if present(cp.STOP):
                line += f", ended {cp.STOP}"
            lines.append(line + ".")
        sections.append(("Plan", "\n".join(lines)))

    return sections


def render_encounter(enc, tables, by_enc):
    patients = tables["patients"].set_index("Id", drop=False)
    providers = tables["providers"].set_index("Id", drop=False)
    orgs = tables["organizations"].set_index("Id", drop=False)

    patient = patients.loc[enc.PATIENT]
    provider = providers.loc[enc.PROVIDER] if enc.PROVIDER in providers.index else None
    org = orgs.loc[enc.ORGANIZATION] if enc.ORGANIZATION in orgs.index else None

    document_type = DOCUMENT_TYPES.get(enc.ENCOUNTERCLASS, "Clinical Note")
    date = enc.START[:10]
    name, _ = patient_line(patient)
    title = f"{document_type} - {name} - {date}"

    return [
        {
            "doc_id": enc.Id,
            "patient_id": enc.PATIENT,
            "document_type": document_type,
            "date": date,
            "section": section,
            "title": title,
            "content": content,
        }
        for section, content in render_sections(enc, patient, provider, org, by_enc)
    ]


def as_text(records):
    """The whole note as a clinician would read it."""
    out = [records[0]["title"], "=" * len(records[0]["title"])]
    for r in records:
        out += ["", r["section"].upper(), r["content"]]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", nargs="?", const="", metavar="ENCOUNTER_ID")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    tables = load_tables()
    by_enc = {name: group_by_encounter(tables[name]) for name in
              ["conditions", "medications", "observations", "procedures",
               "immunizations", "allergies", "careplans"]}
    encounters = tables["encounters"]

    if args.preview is not None:
        if args.preview:
            enc = encounters[encounters.Id == args.preview].iloc[0]
        else:
            # Default preview: a problem visit that has a diagnosis, labs and meds
            has_all = (encounters.Id.isin(by_enc["conditions"])
                       & encounters.Id.isin(by_enc["medications"])
                       & encounters.Id.isin(by_enc["observations"])
                       & (encounters.ENCOUNTERCLASS != "wellness"))
            enc = encounters[has_all].iloc[0]
        records = render_encounter(enc, tables, by_enc)
        print(as_text(records))
        print("\n--- first record as stored:")
        print(json.dumps(records[0], indent=2))
        return

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for enc in encounters.itertuples(index=False):
        records = render_encounter(enc, tables, by_enc)
        path = NOTES_DIR / f"{enc.Id}.json"
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        total += len(records)
    print(f"Wrote {len(encounters)} notes ({total} section records) to {NOTES_DIR}")


if __name__ == "__main__":
    main()
