// mm_touchid.swift -- zeigt den macOS-Dialog "Mit Touch ID entsperren" und
// endet mit 0 (bestaetigt), 1 (abgelehnt/abgebrochen) oder 2 (nicht verfuegbar).
// Uebersetzt der Dienst selbst nach .touchid/Kontor (der Dateiname erscheint im Dialog: "Kontor möchte ...").
// Policy deviceOwnerAuthentication = Touch ID, Apple Watch oder Anmeldepasswort.
import Foundation
import LocalAuthentication

let reason = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "die Finanzübersicht entsperren"
let ctx = LAContext()
var error: NSError?
guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { exit(2) }
let sem = DispatchSemaphore(value: 0)
var ok = false
ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, _ in
    ok = success
    sem.signal()
}
_ = sem.wait(timeout: .now() + 90)
exit(ok ? 0 : 1)
