from __future__ import annotations

from collections.abc import Mapping

SUPPORTED_LANGUAGES = ("de", "en")
LANGUAGE_COOKIE = "cowcloak_lang"

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "landing_eyebrow": "MAIL PRIVACY, SELF-HOSTED",
        "landing_lead": (
            "Create and manage privacy aliases on your own mailcow server "
            "without a second user database."
        ),
        "sign_in": "Sign in with mailcow",
        "aliases_title": "Aliases · Cowcloak",
        "your_aliases": "Your aliases",
        "signed_in_as": "Signed in as {user}",
        "sign_out": "Sign out",
        "create_alias": "Create alias",
        "purpose": "Purpose",
        "purpose_placeholder": "Amazon, hotel, newsletter …",
        "address_style": "Address style",
        "address_style_hint": "Choose how the new address should look.",
        "recommended": "Recommended",
        "readable_random": "Readable random",
        "readable_random_hint": (
            "Neutral and easy to dictate. Uses two words plus a number or three short words."
        ),
        "name_random": "Name + random suffix",
        "name_random_hint": (
            "Starts with the purpose, so you can recognize the service directly from the address."
        ),
        "custom_local_part": "Custom local part",
        "custom_local_part_hint": "Choose the complete part before the @ sign yourself.",
        "custom_address": "Custom address",
        "immutable_hint": (
            "The address is created on {domain} and never changes when you rename its purpose."
        ),
        "show_in_sogo": "Show as sender in SOGo",
        "sogo_create_hint": (
            "Enable this only for aliases you want in the SOGo sender chooser."
        ),
        "create_alias_button": "Create alias",
        "offline_pool": "Offline pool",
        "offline_pool_hint": "Prepare active aliases and keep them in your phone notes.",
        "copy": "Copy",
        "copied": "Copied",
        "delete": "Delete",
        "delete_confirm": (
            "Delete this unused offline alias permanently? Only do this if you have never "
            "handed it out."
        ),
        "copy_all": "Copy all",
        "plain_text": "Open as text",
        "no_prepared_aliases": "No prepared aliases yet.",
        "assigned_aliases": "Assigned aliases",
        "assigned_summary": (
            "{filtered} shown out of {total} aliases pointing exclusively to your mailbox."
        ),
        "search_placeholder": "Search address or purpose",
        "search_aria": "Search aliases",
        "clear_search": "Clear search",
        "filter_all": "All",
        "filter_active": "Active",
        "filter_disabled": "Disabled",
        "filter_aria": "Filter aliases by status",
        "no_purpose": "No purpose",
        "status_active": "Active",
        "status_inactive": "Inactive",
        "status_disabled": "Disabled",
        "sogo_on": "SOGo",
        "sogo_off": "SOGo hidden",
        "sogo_off_short": "SOGo off",
        "edit": "Edit",
        "save": "Save",
        "disable": "Disable",
        "enable": "Enable",
        "edit_sogo_hint": (
            "SOGo visibility controls whether this active alias appears as a selectable sender."
        ),
        "private_comment_hint": (
            "Private mailcow admin comments are not shown or edited. Cowcloak only uses the "
            "private field for its own offline reservation marker."
        ),
        "address_unchanged": "The alias address stays unchanged.",
        "no_search_matches": "No aliases match your search and status filter.",
        "no_assigned_aliases": "No assigned aliases yet.",
        "showing_range": "Showing {start}–{end} of {total}",
        "showing_zero": "Showing 0 aliases",
        "rows_per_page": "Rows per page",
        "apply": "Apply",
        "previous": "Previous",
        "next": "Next",
        "pagination_aria": "Alias pages",
        "assign_prepared": "Assign a prepared alias",
        "assign_hint": (
            "After using one offline, add its purpose here. The private Cowcloak reservation "
            "marker is removed."
        ),
        "used_for_placeholder": "Used for …",
        "assign": "Assign",
        "close": "Close",
        "language": "Language",
    },
    "de": {
        "landing_eyebrow": "E-MAIL-DATENSCHUTZ, SELBST GEHOSTET",
        "landing_lead": (
            "Erstelle und verwalte Datenschutz-Aliase auf deinem eigenen mailcow-Server "
            "ohne eine zweite Benutzerdatenbank."
        ),
        "sign_in": "Mit mailcow anmelden",
        "aliases_title": "Aliase · Cowcloak",
        "your_aliases": "Deine Aliase",
        "signed_in_as": "Angemeldet als {user}",
        "sign_out": "Abmelden",
        "create_alias": "Alias erstellen",
        "purpose": "Verwendungszweck",
        "purpose_placeholder": "Amazon, Hotel, Newsletter …",
        "address_style": "Adressformat",
        "address_style_hint": "Wähle, wie die neue Adresse aussehen soll.",
        "recommended": "Empfohlen",
        "readable_random": "Lesbar zufällig",
        "readable_random_hint": (
            "Neutral und gut diktierbar. Nutzt zwei Wörter plus Zahl oder drei kurze Wörter."
        ),
        "name_random": "Name + Zufallssuffix",
        "name_random_hint": (
            "Beginnt mit dem Verwendungszweck, damit du den Dienst direkt an der Adresse erkennst."
        ),
        "custom_local_part": "Eigener lokaler Teil",
        "custom_local_part_hint": "Bestimme den vollständigen Teil vor dem @-Zeichen selbst.",
        "custom_address": "Eigene Adresse",
        "immutable_hint": (
            "Die Adresse wird auf {domain} erstellt und ändert sich nicht, wenn du den "
            "Verwendungszweck änderst."
        ),
        "show_in_sogo": "In SOGo als Absender anzeigen",
        "sogo_create_hint": (
            "Aktiviere das nur für Aliase, die in der SOGo-Absenderauswahl erscheinen sollen."
        ),
        "create_alias_button": "Alias erstellen",
        "offline_pool": "Offline-Vorrat",
        "offline_pool_hint": (
            "Bereite aktive Aliase vor und speichere sie zum Beispiel in deinen Handynotizen."
        ),
        "copy": "Kopieren",
        "copied": "Kopiert",
        "delete": "Löschen",
        "delete_confirm": (
            "Diesen unbenutzten Offline-Alias dauerhaft löschen? Nur fortfahren, wenn du ihn "
            "noch nie weitergegeben hast."
        ),
        "copy_all": "Alle kopieren",
        "plain_text": "Als Text öffnen",
        "no_prepared_aliases": "Noch keine vorbereiteten Aliase vorhanden.",
        "assigned_aliases": "Zugeordnete Aliase",
        "assigned_summary": (
            "{filtered} von {total} Aliasen werden angezeigt, die ausschließlich auf dein "
            "Postfach zeigen."
        ),
        "search_placeholder": "Adresse oder Verwendungszweck suchen",
        "search_aria": "Aliase durchsuchen",
        "clear_search": "Suche leeren",
        "filter_all": "Alle",
        "filter_active": "Aktiv",
        "filter_disabled": "Deaktiviert",
        "filter_aria": "Aliase nach Status filtern",
        "no_purpose": "Kein Verwendungszweck",
        "status_active": "Aktiv",
        "status_inactive": "Inaktiv",
        "status_disabled": "Deaktiviert",
        "sogo_on": "SOGo",
        "sogo_off": "SOGo ausgeblendet",
        "sogo_off_short": "SOGo aus",
        "edit": "Bearbeiten",
        "save": "Speichern",
        "disable": "Deaktivieren",
        "enable": "Aktivieren",
        "edit_sogo_hint": (
            "Die SOGo-Sichtbarkeit legt fest, ob dieser aktive Alias als auswählbarer "
            "Absender erscheint."
        ),
        "private_comment_hint": (
            "Private mailcow-Admin-Kommentare werden weder angezeigt noch bearbeitet. "
            "Cowcloak nutzt das private Feld nur für seine eigene Offline-Vorratsmarkierung."
        ),
        "address_unchanged": "Die Alias-Adresse bleibt unverändert.",
        "no_search_matches": "Keine Aliase entsprechen der Suche und dem gewählten Status.",
        "no_assigned_aliases": "Noch keine zugeordneten Aliase vorhanden.",
        "showing_range": "Zeige {start}–{end} von {total}",
        "showing_zero": "Zeige 0 Aliase",
        "rows_per_page": "Zeilen pro Seite",
        "apply": "Übernehmen",
        "previous": "Zurück",
        "next": "Weiter",
        "pagination_aria": "Alias-Seiten",
        "assign_prepared": "Vorbereiteten Alias zuordnen",
        "assign_hint": (
            "Wenn du einen Offline-Alias verwendet hast, trage hier seinen Zweck ein. "
            "Die private Cowcloak-Vorratsmarkierung wird dabei entfernt."
        ),
        "used_for_placeholder": "Verwendet für …",
        "assign": "Zuordnen",
        "close": "Schließen",
        "language": "Sprache",
    },
}


def detect_language(cookie_value: str | None, accept_language: str | None) -> str:
    if cookie_value in SUPPORTED_LANGUAGES:
        return cookie_value

    preferred = (accept_language or "").split(",", 1)[0].strip().lower()
    return "de" if preferred == "de" or preferred.startswith("de-") else "en"


def translations(language: str) -> Mapping[str, str]:
    return _TRANSLATIONS.get(language, _TRANSLATIONS["en"])
