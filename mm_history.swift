// mm_historie.swift -- fragt das MoneyMoney-Passwort in einem macOS-Dialog ab und gibt NUR daraus abgeleitete
// Datenbank-Schluessel aus (PBKDF2 mit dem Salz der Datenbank). Das Passwort verlaesst diesen Prozess nie:
// keine Befehlszeile, keine Datei, keine Umgebungsvariable, keine Ausgabe.
// Der Dienst uebersetzt ihn nur fuer den Vorgang in einen privaten Ordner (Name "Kontor" = Programmname im Fenster)
// und loescht ihn danach.
//
// Aufruf:  Kontor <salz-hex> <hash>:<runden> [<hash>:<runden> ...]     hash = sha1 | sha512
// Ausgabe: je Parameter eine Zeile mit dem 32-Byte-Schluessel als Hex.
// Ende:    0 = ok, 1 = abgebrochen, 2 = Fehler.
import AppKit
import CommonCrypto
import Foundation

func bytes(fromHex s: String) -> [UInt8]? {
    var out: [UInt8] = []
    var it = s.makeIterator()
    while let a = it.next() {
        guard let b = it.next(), let v = UInt8(String([a, b]), radix: 16) else { return nil }
        out.append(v)
    }
    return out
}

let args = CommandLine.arguments
guard args.count >= 3, let salt = bytes(fromHex: args[1]), salt.count == 16 else { exit(2) }
var specs: [(CCPseudoRandomAlgorithm, UInt32)] = []
for a in args.dropFirst(2) {
    let p = a.split(separator: ":")
    guard p.count == 2, let rounds = UInt32(p[1]), rounds >= 1000 else { exit(2) }
    let alg = p[0] == "sha512" ? CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA512) : CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA1)
    specs.append((alg, rounds))
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let alert = NSAlert()
alert.messageText = "Kontostände aus MoneyMoney einlesen"
alert.informativeText = "Gib dein MoneyMoney-Passwort ein. Es bleibt in diesem Fenster: Kontor erhält nur einen daraus berechneten Schlüssel, öffnet die Datenbank damit einmalig nur lesend im Arbeitsspeicher und verwirft ihn danach. In MoneyMoney wird nichts verändert."
alert.addButton(withTitle: "Einlesen")
alert.addButton(withTitle: "Abbrechen")
let field = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
field.placeholderString = "MoneyMoney-Passwort"
alert.accessoryView = field
alert.window.initialFirstResponder = field
app.activate(ignoringOtherApps: true)
guard alert.runModal() == .alertFirstButtonReturn else { exit(1) }

var pw = Array(field.stringValue.utf8)
field.stringValue = ""
guard !pw.isEmpty else { exit(1) }

var lines: [String] = []
for (alg, rounds) in specs {
    var key = [UInt8](repeating: 0, count: 32)
    let status = pw.withUnsafeBufferPointer { p -> Int32 in
        p.baseAddress!.withMemoryRebound(to: CChar.self, capacity: p.count) { cp in
            CCKeyDerivationPBKDF(CCPBKDFAlgorithm(kCCPBKDF2), cp, p.count, salt, salt.count, alg, rounds, &key, key.count)
        }
    }
    guard status == 0 else { _ = memset_s(&pw, pw.count, 0, pw.count); exit(2) }
    lines.append(key.map { String(format: "%02x", $0) }.joined())
    _ = memset_s(&key, key.count, 0, key.count)
}
_ = memset_s(&pw, pw.count, 0, pw.count)
FileHandle.standardOutput.write((lines.joined(separator: "\n") + "\n").data(using: .utf8)!)
exit(0)
