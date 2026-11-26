import re


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_records(records, rules):
    validated = []
    seen = set()

    for record in records:
        errors = []
        warnings = []
        key = (
            record.get("adherent"),
            record.get("num_bulletin"),
            record.get("ligne"),
        )
        if key in seen:
            errors.append("Doublon de la ligne, de l'adherent et du numero bulletin.")
        seen.add(key)

        for field in ("ligne", "adherent", "num_bulletin", "correction_proposee"):
            if record.get(field) is None:
                errors.append(f"Valeur manquante : {field}.")

        adherent = record.get("adherent")
        if adherent and not IDENTIFIER_RE.fullmatch(str(adherent)):
            errors.append("Identifiant adherent incompatible.")

        bulletin = record.get("num_bulletin")
        if bulletin and not str(bulletin).isdigit():
            errors.append("Le numero bulletin doit être composé de chiffres.")

        code = record.get("type_erreur")
        rule = rules.get(code) if isinstance(rules, dict) else None
        if code not in (1, 2, 3, 9):
            errors.append("Code erreur inconnu.")
        elif not rule or not rule.get("active"):
            errors.append("Aucune règle métier validée pour ce code.")

        if record.get("correction_proposee") is not None:
            correction = str(record["correction_proposee"])
            if not correction.isdigit():
                warnings.append("La correction proposée contient des caractères autres que des chiffres.")

        status = "ERROR" if errors else ("WARNING" if warnings else "VALID")
        item = dict(record)
        item["status"] = status
        item["errors"] = errors
        item["warnings"] = warnings
        validated.append(item)
    return validated
