from __future__ import annotations

from pathlib import Path
from openpyxl import load_workbook


REQUIRED_COLUMNS = {
    "ligne": ("ligne etat",),
    "adherent": ("adherant", "adhérent", "adherent"),
    "num_bulletin": ("num bulletin",),
    "type_erreur": ("type erreur",),
    "correction_proposee": ("correction proposé", "correction proposee"),
    "observation": ("observation",),
}


def normalize_header(value):
    if value is None:
        return ""
    return (
        str(value).strip().lower()
        .replace("é", "e").replace("è", "e").replace("ê", "e")
        .replace("ë", "e").replace("à", "a").replace("â", "a")
        .replace("ô", "o").replace("ù", "u").replace("û", "u")
        .replace("ç", "c")
    )


def scalar_text(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    return text or None


class ExcelReaderError(ValueError):
    pass


def find_header_column(headers, field):
    normalized = [normalize_header(value) for value in headers]
    for candidate in REQUIRED_COLUMNS[field]:
        try:
            return normalized.index(normalize_header(candidate))
        except ValueError:
            continue
    return None


def extract_error_referential(sheet):
    labels = {}
    for row in range(1, sheet.max_row + 1):
        code = sheet.cell(row, 11).value
        label = sheet.cell(row, 10).value
        if isinstance(code, (int, float)) and isinstance(label, str):
            labels[int(code)] = label.strip()
        elif isinstance(code, str) and code.strip().isdigit() and isinstance(label, str):
            labels[int(code)] = label.strip()
    return labels


def infer_year(sheet_name, referential):
    if sheet_name.isdigit():
        year = int(sheet_name)
        if 1900 <= year <= 2200:
            return year
    if 2026 in referential.values():
        return 2026
    return None


def read_excel(path: str | Path, sheet_name: str | None = None):
    path = Path(path)
    if not path.exists():
        raise ExcelReaderError("Le fichier Excel est introuvable.")
    if path.suffix.lower() != ".xlsx":
        raise ExcelReaderError("Le fichier doit être au format XLSX.")

    workbook = load_workbook(path, data_only=True)
    selected = sheet_name or (workbook.sheetnames[0] if workbook.sheetnames else None)
    if not selected or selected not in workbook.sheetnames:
        raise ExcelReaderError("La feuille Excel demandée est introuvable.")

    sheet = workbook[selected]
    header_row = 1
    headers = [sheet.cell(header_row, column).value for column in range(1, sheet.max_column + 1)]
    columns = {}
    missing = []
    for field in REQUIRED_COLUMNS:
        index = find_header_column(headers, field)
        if index is None:
            missing.append(field)
        else:
            columns[field] = index + 1
    if missing:
        raise ExcelReaderError(
            "Colonnes obligatoires manquantes : " + ", ".join(missing)
        )

    referential = extract_error_referential(sheet)
    records = []
    for excel_row in range(header_row + 1, sheet.max_row + 1):
        values = {
            field: sheet.cell(excel_row, column).value
            for field, column in columns.items()
        }
        if all(value is None for value in values.values()):
            continue
        code_value = scalar_text(values["type_erreur"])
        try:
            code = int(code_value) if code_value is not None else None
        except (TypeError, ValueError):
            code = None
        records.append({
            "ligne": scalar_text(values["ligne"]),
            "adherent": scalar_text(values["adherent"]),
            "num_bulletin": scalar_text(values["num_bulletin"]),
            "type_erreur": code,
            "type_erreur_libelle": referential.get(code),
            "correction_proposee": scalar_text(values["correction_proposee"]),
            "observation": scalar_text(
                sheet.cell(excel_row, find_header_column(headers, "observation") + 1).value
                if find_header_column(headers, "observation") is not None
                else None
            ),
        })

    return {
        "source_file": path.name,
        "sheet": selected,
        "sheets": workbook.sheetnames,
        "year_hint": infer_year(selected, referential),
        "error_referential": referential,
        "records": records,
    }
