"""Guard rails for Claude working on Kontor (PreToolUse hook): on the user's Mac never touch Kontor's data folder or
MoneyMoney's own data, never use MoneyMoney's transfer commands; nowhere force-push or delete main. Exit code 2 blocks
the call and tells Claude why; anything else lets the normal flow go on. A guard rail, not a sandbox."""
import json
import re
import sys

ALLOWED = "KONTOR_DATEN_ERLAUBT"        # only after the user explicitly allowed it in this session

RULES = [
    # (only for tools on the Mac, can the user allow it, pattern, reason)
    (True, True, r"Application Support/Kontor\b",
     "Kontors Datenordner am Mac nur mit ausdrücklicher Erlaubnis des Nutzers (dann %s in den Befehl schreiben)." % ALLOWED),
    (True, False, r"com\.moneymoney-app|MoneyMoney\.sqlite|Containers/[^\"']*MoneyMoney",
     "MoneyMoneys eigene Daten liest Kontor nur über den Upload in der Oberfläche – nie direkt."),
    (True, False, r"(?i)create\s*(bank|batch)\s*transfer|create\s*(batch\s*)?direct\s*debit",
     "Überweisungen und Lastschriften sind gesperrt."),
    (False, False, r"git\s+push\b[^\n;&|]*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s--delete\b|\s\+?:main\b|\s\+\S*main\b)",
     "Kein Force-Push und kein Löschen von main."),
]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = str(data.get("tool_name") or "")
    text = json.dumps(data.get("tool_input") or {}, ensure_ascii=False).replace("\\\\", "").replace("\\", "")
    on_mac = tool.startswith("mcp__remote-devices__")
    for mac_only, can_allow, pattern, reason in RULES:
        if mac_only and not on_mac:
            continue
        if re.search(pattern, text) and not (can_allow and ALLOWED in text):
            print("Gesperrt: " + reason, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
