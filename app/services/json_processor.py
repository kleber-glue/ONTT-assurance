from datetime import date


def build_json_payload(extracted, numero_bordereau, annee):
    return {
        "metadata": {
            "source_file": extracted["source_file"],
            "sheet": extracted["sheet"],
            "numero_bordereau": str(numero_bordereau).strip(),
            "annee": int(annee),
            "date_traitement": date.today().isoformat(),
            "total_records": len(extracted["records"]),
            "format_version": "1.0",
        },
        "records": extracted["records"],
    }
