// Kontor's pages in macOS's own WebKit -- the engine of Kontor's Mac app -- driven like a person: steps from a file (run a script in
// the page, a right click on an element, wait), the answers as one JSON array on stdout. Built and run only by
// tests/test_mac_webview.py on GitHub's Mac (what Playwright's WebKit on Linux does not do the same way: a right click selects the
// word under the pointer there, menus, scrolling). Never part of the app; it opens only the address it is given.
//
//   mac_webview <url> <steps.json>      steps: [{"js": "<body of an async function>"}, {"right": "<css selector>"}, {"wait": ms}]
import AppKit
import WebKit

final class Driver: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    let url: URL
    var steps: [[String: Any]]
    var out: [Any] = []
    var window: NSWindow!
    var web: WKWebView!

    init(url: URL, steps: [[String: Any]]) {
        self.url = url
        self.steps = steps
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let conf = WKWebViewConfiguration()
        conf.websiteDataStore = WKWebsiteDataStore.nonPersistent()
        conf.applicationNameForUserAgent = "KontorApp/1"            // as the app: the page behaves as it does there
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1320, height: 860), configuration: conf)
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860), styleMask: [.titled, .closable, .resizable],
                          backing: .buffered, defer: false)
        window.contentView = web
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 240) { self.finish(error: "timeout") }
        web.load(URLRequest(url: url))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if out.isEmpty && !steps.isEmpty { next() }
    }

    func next() {
        guard !steps.isEmpty else { finish(error: nil); return }
        let s = steps.removeFirst()
        if let js = s["js"] as? String {
            web.callAsyncJavaScript(js, arguments: [:], in: nil, in: WKContentWorld.page) { r in
                switch r {
                case .success(let v): self.out.append(v ?? NSNull())
                case .failure(let e): self.out.append(["error": String(describing: e)])
                }
                self.next()
            }
        } else if let sel = s["right"] as? String {
            // where the element is (CSS pixels from the top left of the page's view), then a right click there -- as the mouse sends it
            let q = "const el = document.querySelector(\(Driver.quote(sel))); if (!el) return null; el.scrollIntoView({block: 'center'}); "
                + "const b = el.getBoundingClientRect(); return [b.left + Math.min(b.width / 2, 12), b.top + b.height / 2];"
            web.callAsyncJavaScript(q, arguments: [:], in: nil, in: WKContentWorld.page) { r in
                guard case .success(let v) = r, let xy = v as? [Double], xy.count == 2 else {
                    self.out.append(["error": "no element: " + sel]); self.next(); return
                }
                let z = Double(self.web.pageZoom)
                let local = NSPoint(x: xy[0] * z, y: self.web.isFlipped ? xy[1] * z : Double(self.web.bounds.height) - xy[1] * z)
                let p = self.web.convert(local, to: nil)
                for type in [NSEvent.EventType.rightMouseDown, .rightMouseUp] {
                    if let e = NSEvent.mouseEvent(with: type, location: p, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                                  windowNumber: self.window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1) {
                        self.window.sendEvent(e)
                    }
                }
                self.out.append(["clicked": sel])
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.next() }
            }
        } else if let ms = s["wait"] as? Double {
            DispatchQueue.main.asyncAfter(deadline: .now() + ms / 1000) { self.next() }
        } else {
            out.append(["error": "unknown step"])
            next()
        }
    }

    static func quote(_ s: String) -> String {
        let d = (try? JSONSerialization.data(withJSONObject: [s])) ?? Data("[\"\"]".utf8)
        let t = String(data: d, encoding: .utf8) ?? "[\"\"]"
        return String(t.dropFirst().dropLast())
    }

    func finish(error: String?) {
        var all: [String: Any] = ["steps": out]
        if let e = error { all["error"] = e }
        let d = (try? JSONSerialization.data(withJSONObject: all, options: [.sortedKeys])) ?? Data("{}".utf8)
        FileHandle.standardOutput.write(d)
        FileHandle.standardOutput.write(Data("\n".utf8))
        exit(error == nil ? 0 : 1)
    }
}

let args = CommandLine.arguments
guard args.count == 3, let url = URL(string: args[1]), ["127.0.0.1", "localhost"].contains(url.host ?? ""),
      let data = FileManager.default.contents(atPath: args[2]),
      let steps = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else {
    FileHandle.standardError.write(Data("usage: mac_webview http://127.0.0.1:<port>/ steps.json\n".utf8))
    exit(2)
}
let app = NSApplication.shared
let driver = Driver(url: url, steps: steps)
app.delegate = driver
app.setActivationPolicy(.accessory)
app.run()
