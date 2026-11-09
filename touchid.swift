// touchid.swift -- zeigt den macOS-Dialog "Mit Touch ID entsperren" und
// endet mit 0 (bestaetigt), 1 (abgelehnt/abgebrochen) oder 2 (nicht verfuegbar).
// Uebersetzt der Dienst selbst nach .touchid/Kontor.app (der Name erscheint im Dialog: "Kontor möchte ...").
// Policy deviceOwnerAuthentication = Touch ID, Apple Watch oder Anmeldepasswort.
// Started through LaunchServices (auth.py: "open"), the app comes to the front with keyboard focus, so Touch ID works without a
// click on the dialog. After a confirmed Touch ID it writes "ok <nonce>" (the nonce of the request) to its standard output.
import AppKit
import LocalAuthentication

let args = CommandLine.arguments
let reason = args.count > 1 ? args[1] : "die Finanzübersicht entsperren"
let nonce = args.count > 2 ? args[2] : ""
let ctx = LAContext()
var error: NSError?
guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { exit(2) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {
    app.activate(ignoringOtherApps: true)
    ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, _ in
        DispatchQueue.main.async {
            if success { print("ok \(nonce)"); fflush(stdout) }
            exit(success ? 0 : 1)
        }
    }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 90) { exit(1) }
app.run()
