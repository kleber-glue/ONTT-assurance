import re


ORACLE_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_$#]*$", re.I)

ORACLE_IDENTIFIER_FIELDS = {
    "table_name": "Nom de la table Oracle",
    "update_column": "Colonne de mise à jour",
    "identifier_column": "Colonne identifiant",
    "adherent_column": "Colonne adhérent",
    "bulletin_column": "Colonne numéro bulletin",
    "bordereau_column": "Colonne numéro bordereau",
}


def validate_oracle_identifier(name):
    return bool(name and ORACLE_IDENTIFIER.fullmatch(name))


def validate_oracle_identifier_fields(configuration):
    for field, label in ORACLE_IDENTIFIER_FIELDS.items():
        value = (configuration.get(field) or "").strip()
        if value and not validate_oracle_identifier(value):
            raise ValueError(
                f"{label} : « {value} » n'est pas un nom Oracle valide "
                "(lettre au début, puis lettres, chiffres, _, $ ou #)."
            )


def oracle_literal(value, oracle_type="VARCHAR2"):
    if value is None:
        return "NULL"
    oracle_type = (oracle_type or "VARCHAR2").upper()
    if oracle_type.startswith(("NUMBER", "INTEGER")):
        text = str(value).strip()
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
            raise ValueError(f"Valeur incompatible avec le type Oracle {oracle_type}.")
        return text
    return "'" + str(value).replace("'", "''") + "'"


def generate_sql(payload, validated_records, rules, global_config):
    statements = []
    rejected = []

    correspondence_groups = (
        [global_config] if isinstance(global_config, dict) else global_config
    )
    if not correspondence_groups:
        raise ValueError("Configurez au moins une correspondance Oracle.")
    for group in correspondence_groups:
        tables = group["tables"] if "tables" in group else [group]
        if not tables:
            raise ValueError("Ajoutez au moins une table à chaque correspondance globale.")
        for table in tables:
            table_name = (table.get("table_name") or "").strip()
            if not table_name:
                raise ValueError("Le nom de la table Oracle n'est pas configuré.")
            validate_oracle_identifier_fields(table)

    for record in validated_records:
        if record["status"] == "ERROR":
            rejected.append(record)
            continue

        code = record["type_erreur"]
        rule = rules.get(code)
        if not rule or not rule["active"]:
            continue

        for group in correspondence_groups:
            configured_error_type = group.get("error_type")
            if (
                configured_error_type is not None
                and str(configured_error_type) != str(code)
            ):
                continue

            tables = group["tables"] if "tables" in group else [group]
            for correspondence in tables:
                table_name = (correspondence.get("table_name") or "").strip()
                update_column = (
                    rule["update_column"] or correspondence.get("update_column")
                )
                identifier_column = (
                    rule["identifier_column"]
                    or correspondence.get("identifier_column")
                )
                bulletin_column = correspondence.get("bulletin_column")
                adherent_column = correspondence.get("adherent_column")
                bordereau_column = correspondence.get("bordereau_column")
                complement = (
                    rule["complement"]
                    or correspondence.get("complementary_where")
                )

                for field, column in (
                    ("update_column", update_column),
                    ("identifier_column", identifier_column),
                ):
                    if column and not validate_oracle_identifier(column):
                        label = ORACLE_IDENTIFIER_FIELDS[field]
                        raise ValueError(
                            f"{label} de la règle {code} : « {column} » "
                            "n'est pas un nom Oracle valide."
                        )
                if not update_column or not identifier_column:
                    raise ValueError(
                        "La colonne de mise à jour et la colonne identifiant sont obligatoires."
                    )

                where_parts = []
                identifier = record.get("ligne")
                where_parts.append(f"{identifier_column} = {oracle_literal(identifier)}")
                if adherent_column:
                    where_parts.append(
                        f"{adherent_column} = {oracle_literal(record['adherent'])}"
                    )
                if bulletin_column:
                    where_parts.append(
                        f"{bulletin_column} = {oracle_literal(record['num_bulletin'])}"
                    )
                if bordereau_column:
                    where_parts.append(
                        f"{bordereau_column} = "
                        f"{oracle_literal(payload['metadata']['numero_bordereau'])}"
                    )
                if complement:
                    where_parts.append(complement)

                if not where_parts:
                    raise ValueError("Une clause WHERE suffisamment précise est obligatoire.")

                oracle_type = (
                    rule["oracle_type"]
                    or correspondence.get("oracle_type")
                    or "VARCHAR2"
                )
                value = oracle_literal(record["correction_proposee"], oracle_type)
                statements.append(
                    f"UPDATE {table_name}\n"
                    f"SET {update_column} = {value}\n"
                    f"WHERE " + "\n  AND ".join(where_parts) + ";"
                )

    return statements, rejected


def build_sql_document(payload, statements):
    metadata = payload["metadata"]
    lines = [
        "-- Script généré automatiquement",
        f"-- Numero de bordereau : {metadata['numero_bordereau']}",
        f"-- Annee : {metadata['annee']}",
        f"-- Fichier source : {metadata['source_file']}",
        f"-- Feuille : {metadata['sheet']}",
        f"-- Date de generation : {metadata['date_traitement']}",
        f"-- Nombre d'instructions : {len(statements)}",
        "-- Vérifier le nombre de lignes modifiées avant COMMIT.",
        "",
    ]
    lines.extend([statement + "\n" for statement in statements])
    lines.extend([
        "-- Vérification recommandée:",
        "-- SELECT COUNT(*) FROM la_table WHERE vos_conditions;",
        "-- Utiliser ROLLBACK pour annuler; ne pas exécuter COMMIT automatiquement.",
    ])
    return "\n".join(lines)
