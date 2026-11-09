// touchid.swift -- zeigt den macOS-Dialog "Mit Touch ID entsperren" und
// endet mit 0 (bestaetigt), 1 (abgelehnt/abgebrochen) oder 2 (nicht verfuegbar).
// Uebersetzt der Dienst selbst nach .touchid/Kontor (der Dateiname erscheint im Dialog: "Kontor möchte ...").
// Policy deviceOwnerAuthentication = Touch ID, Apple Watch oder Anmeldepasswort.
// A small accessory app (no Dock icon) that brings itself to the front first, so the dialog appears in front of the browser
// or web app window instead of behind it.
import AppKit
import LocalAuthentication

let reason = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "die Finanzübersicht entsperren"
let ctx = LAContext()
var error: NSError?
guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { exit(2) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {
    app.activate(ignoringOtherApps: true)
    ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, _ in
        DispatchQueue.main.async { exit(success ? 0 : 1) }
    }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 90) { exit(1) }
app.run()
