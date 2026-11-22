// touchid.swift -- zeigt den macOS-Dialog "Mit Touch ID entsperren" und
// endet mit 0 (bestaetigt), 1 (abgelehnt/abgebrochen) oder 2 (nicht verfuegbar).
// Uebersetzt der Dienst selbst nach .touchid/Kontor.app (der Name erscheint im Dialog: "Kontor möchte ...").
// Policy deviceOwnerAuthentication = Touch ID, Apple Watch oder Anmeldepasswort.
// Started through LaunchServices (auth.py: "open"), the app comes to the front with keyboard focus, so Touch ID works without a
// click on the dialog. After a confirmed Touch ID it writes "ok <nonce>" (the nonce of the request) to its standard output.
//
// The data key (auth.py, access.py): three more modes, each with values Kontor made itself.
//   --create                     a new key in the Secure Enclave, usable only with Touch ID or the Mac's password, only on this
//                                Mac (making it asks nothing): prints its handle and its public key (base64)
//   --seal <public> <salt>       a fresh key pair against that public key: prints the fresh public key (base64) and the shared
//                                key (HKDF-SHA256, 32 bytes, hex) -- Kontor wraps the data key with it; asks nothing
//   --unseal <reason> <nonce> <handle> <fresh public> <salt> <transport public>
//                                the same shared key again, through the Secure Enclave's key -- macOS asks for Touch ID (or the
//                                Mac's password) first; only then prints "ok <nonce> <public> <wrapped key> <tag>": the key
//                                wrapped for this request (X25519 with Kontor's transport key, HKDF-SHA256 to a pad and an
//                                HMAC key) -- the output goes through a file, what is in it is of no use to anyone else.
//                                "gone <nonce>": this Mac's Secure Enclave cannot use the handle (made on another Mac).
//   --transport-check <key> <transport public> <nonce>
//                                for the tests: wraps a made-up key (hex) exactly as --unseal does -- no key of this Mac is used
import AppKit
import CryptoKit
import LocalAuthentication
import Security

let args = CommandLine.arguments
let info = Data("kontor-touchid-v1".utf8)

func hexBytes(_ s: String) -> Data? {
    guard s.count % 2 == 0 else { return nil }
    var out = Data()
    var i = s.startIndex
    while i < s.endIndex {
        let j = s.index(i, offsetBy: 2)
        guard let b = UInt8(s[i..<j], radix: 16) else { return nil }
        out.append(b)
        i = j
    }
    return out
}

func hex(_ d: Data) -> String {
    return d.map { String(format: "%02x", $0) }.joined()
}

func derivedBytes(_ shared: SharedSecret, _ salt: Data) -> Data {
    let key = shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: salt, sharedInfo: info, outputByteCount: 32)
    return key.withUnsafeBytes { Data($0) }
}

func derived(_ shared: SharedSecret, _ salt: Data) -> String {
    return hex(derivedBytes(shared, salt))
}

// the key wrapped for one request: X25519 with Kontor's transport key, HKDF-SHA256 (salt: the nonce) to a pad and an HMAC key
func wrapped(_ key: Data, for transport: Data, nonce: String) -> String? {
    guard key.count == 32, let theirs = try? Curve25519.KeyAgreement.PublicKey(rawRepresentation: transport) else { return nil }
    let mine = Curve25519.KeyAgreement.PrivateKey()
    guard let shared = try? mine.sharedSecretFromKeyAgreement(with: theirs) else { return nil }
    let okm = shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: Data(nonce.utf8), sharedInfo: Data("kontor-touchid-transport-v1".utf8),
                                             outputByteCount: 64).withUnsafeBytes { Data($0) }
    let ct = Data(zip(key, okm.prefix(32)).map { $0 ^ $1 })
    let tag = Data(HMAC<SHA256>.authenticationCode(for: ct, using: SymmetricKey(data: okm.suffix(32))))
    return "\(mine.publicKey.rawRepresentation.base64EncodedString()) \(hex(ct)) \(hex(tag))"
}

if args.count == 2 && args[1] == "--create" {
    guard SecureEnclave.isAvailable,
          let access = SecAccessControlCreateWithFlags(nil, kSecAttrAccessibleWhenUnlockedThisDeviceOnly, [.privateKeyUsage, .userPresence], nil),
          let key = try? SecureEnclave.P256.KeyAgreement.PrivateKey(accessControl: access) else { exit(2) }
    print(key.dataRepresentation.base64EncodedString() + " " + key.publicKey.x963Representation.base64EncodedString())
    exit(0)
}
if args.count == 5 && args[1] == "--transport-check" {
    guard let key = hexBytes(args[2]), let transport = Data(base64Encoded: args[3]), let line = wrapped(key, for: transport, nonce: args[4]) else { exit(2) }
    print(line)
    exit(0)
}
if args.count == 4 && args[1] == "--seal" {
    guard let raw = Data(base64Encoded: args[2]), let salt = hexBytes(args[3]),
          let pub = try? P256.KeyAgreement.PublicKey(x963Representation: raw) else { exit(2) }
    let fresh = P256.KeyAgreement.PrivateKey()
    guard let shared = try? fresh.sharedSecretFromKeyAgreement(with: pub) else { exit(2) }
    print(fresh.publicKey.x963Representation.base64EncodedString() + " " + derived(shared, salt))
    exit(0)
}

let unseal = args.count == 8 && args[1] == "--unseal"
let reason = unseal ? args[2] : (args.count > 1 ? args[1] : "die Finanzübersicht entsperren")
let nonce = unseal ? args[3] : (args.count > 2 ? args[2] : "")
let ctx = LAContext()
var error: NSError?
guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else { exit(2) }
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {
    app.activate(ignoringOtherApps: true)
    if unseal {
        // the Secure Enclave's key asks macOS for Touch ID (or the Mac's password) itself, with this text
        DispatchQueue.global(qos: .userInitiated).async {
            ctx.localizedReason = reason
            guard let handle = Data(base64Encoded: args[4]),
                  let key = try? SecureEnclave.P256.KeyAgreement.PrivateKey(dataRepresentation: handle, authenticationContext: ctx) else {
                DispatchQueue.main.async { print("gone \(nonce)"); fflush(stdout); exit(3) }
                return
            }
            let out: String? = {
                guard let raw = Data(base64Encoded: args[5]), let salt = hexBytes(args[6]), let transport = Data(base64Encoded: args[7]),
                      let pub = try? P256.KeyAgreement.PublicKey(x963Representation: raw),
                      let shared = try? key.sharedSecretFromKeyAgreement(with: pub) else { return nil }
                return wrapped(derivedBytes(shared, salt), for: transport, nonce: nonce)
            }()
            DispatchQueue.main.async {
                if let o = out { print("ok \(nonce) \(o)"); fflush(stdout) }
                exit(out != nil ? 0 : 1)
            }
        }
        return
    }
    ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, _ in
        DispatchQueue.main.async {
            if success { print("ok \(nonce)"); fflush(stdout) }
            exit(success ? 0 : 1)
        }
    }
}
DispatchQueue.main.asyncAfter(deadline: .now() + 90) { exit(1) }
app.run()
