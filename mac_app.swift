// mac_app.swift -- Kontor as an app of its own on the Mac: a window with Apple's WebKit (Safari's engine) around Kontor's
// interface on this Mac. Built here by mac_app.py (like the Touch ID helper) into Kontor.app in the program folder.
//
// Why an app of its own: Safari's web app in the Dock keeps the page's microphone grant only while it runs (and 10 minutes
// after the last recording), so it asks again and again. Here the app decides: Kontor's own page -- its address on this
// Mac, the main frame -- gets the microphone without asking; macOS asks once, for this app. Nothing else ever runs in it:
// any other address opens in the browser.
//
// No words of its own: the menu's words come from the page (mac_app labels in web/i18n.js), the microphone text from
// Info.plist (mac_app.py). Kontor's address comes from the service (`defaults write local.kontor.app url …`), only ever
// http://127.0.0.1:<port>/. `--check <url>`: loads it, prints what the page sees of the app, quits (the tests on GitHub's Mac).
import AppKit
import AVFoundation
import WebKit

let prefs = UserDefaults.standard

func kontorAddress() -> URL {
    if let s = prefs.string(forKey: "url"), let u = URL(string: s), u.scheme == "http", u.host == "127.0.0.1", u.port != nil { return u }
    return URL(string: "http://127.0.0.1:8765/")!
}

// The window has no title bar of its own: the page reaches up to the window's top edge, its title row beside the window
// buttons. The strip where the title bar was moves the window, as a title bar does -- except where the page has something to
// click in it (the page says where: holes, in its own px); a double click does what macOS is set to (zoom, minimize, nothing).
final class Web: WKWebView {
    var band: CGFloat = 0           // the strip's height (points); 0: none (full screen, or a window with its title bar)
    var holes: [CGRect] = []

    private func inBand(_ e: NSEvent) -> Bool {
        guard band > 0, magnification == 1, let w = window, !w.styleMask.contains(.fullScreen) else { return false }
        let p = convert(e.locationInWindow, from: nil)
        let top = isFlipped ? p.y : bounds.height - p.y
        guard top >= 0, top < band else { return false }
        let q = CGPoint(x: p.x / pageZoom, y: top / pageZoom)
        return !holes.contains { $0.insetBy(dx: -2, dy: -2).contains(q) }
    }

    override func acceptsFirstMouse(for e: NSEvent?) -> Bool {
        if let e = e, inBand(e) { return true }         // moving a window in the background, as by its title bar
        return super.acceptsFirstMouse(for: e)
    }

    override func mouseDown(with e: NSEvent) {
        guard inBand(e), let w = window else { super.mouseDown(with: e); return }
        if e.clickCount == 2 {
            switch UserDefaults.standard.string(forKey: "AppleActionOnDoubleClick") {
            case "Minimize": w.performMiniaturize(nil)
            case "None": break
            default: w.performZoom(nil)
            }
            return
        }
        w.performDrag(with: e)
    }
}

final class Shell: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuItemValidation, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandlerWithReply {
    private var window: NSWindow!
    private var web: Web!
    private var home = kontorAddress()
    private var labels: [String: String] = (prefs.dictionary(forKey: "labels") as? [String: String]) ?? [:]
    private var commands: [[String: Any]] = ((prefs.array(forKey: "commands") as? [[String: Any]]) ?? []).compactMap { Shell.parseCommand($0) }
    private var enabled = Set<String>()
    private var popups: [NSWindow] = []
    private var watches: [NSKeyValueObservation] = []
    private var printed: (() -> Void)?
    private let check: String?

    init(check: String?) {
        self.check = check
        super.init()
    }

    // MARK: start

    func applicationDidFinishLaunching(_ notification: Notification) {
        let conf = WKWebViewConfiguration()
        conf.websiteDataStore = WKWebsiteDataStore.default()
        conf.applicationNameForUserAgent = "KontorApp/1"
        conf.mediaTypesRequiringUserActionForPlayback = []
        conf.userContentController.addScriptMessageHandler(self, contentWorld: WKContentWorld.page, name: "kontor")
        conf.userContentController.addUserScript(WKUserScript(source: Shell.bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web = Web(frame: NSRect(x: 0, y: 0, width: 1320, height: 860), configuration: conf)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsMagnification = true
        web.allowsBackForwardNavigationGestures = false
        if let z = prefs.object(forKey: "zoom") as? Double { web.pageZoom = CGFloat(z) }

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
        window.title = "Kontor"
        window.contentView = web
        window.minSize = NSSize(width: 380, height: 480)
        window.isReleasedWhenClosed = false
        window.tabbingMode = .disallowed
        window.delegate = self
        if !window.setFrameUsingName("Kontor") { window.center() }
        window.setFrameAutosaveName("Kontor")
        noTitleBar()
        watches.append(web.observe(\.title, options: [.new]) { [weak self] w, _ in
            if let t = w.title, !t.isEmpty { self?.window.title = t; self?.placeButtons() }          // (a new title lays the bar out anew)
        })
        buildMenu()

        if let c = check {          // only Kontor's own address -- no other page ever gets in here (shown too: WebKit gives the microphone to a page on screen only)
            guard URL(string: c) == home else { Shell.report("{\"error\": \"not Kontor's address\"}", ok: false) }
            DispatchQueue.main.asyncAfter(deadline: .now() + 45) { Shell.report("{\"error\": \"timeout\"}", ok: false) }
        }
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(web)
        activate()
        web.load(URLRequest(url: home))
    }

    // no title bar: the page to the window's top edge -- only if clicks there really reach the page (else its title row could not
    // be used): then the window keeps its title bar
    private func noTitleBar() {
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        if #available(macOS 11.0, *) { window.titlebarSeparatorStyle = .none }
        web.band = window.frame.height - window.contentLayoutRect.height
        if web.band > 0 { placeButtons() }
        if web.band > 0 && stripReachesPage() { return }
        window.styleMask.remove(.fullSizeContentView)
        window.titlebarAppearsTransparent = false
        window.titleVisibility = .visible
        web.band = 0
    }

    private func stripReachesPage() -> Bool {
        guard let frame = window.contentView?.superview else { return false }
        frame.layoutSubtreeIfNeeded()
        let p = web.convert(NSPoint(x: web.bounds.midX, y: web.isFlipped ? web.band / 2 : web.bounds.height - web.band / 2), to: nil)
        guard let v = frame.hitTest(frame.superview.map { $0.convert(p, from: nil) } ?? p) else { return false }
        return v === web || v.isDescendant(of: web)
    }

    // the window buttons level with the page's title row: its middle 30px from the top (the page's .topbar: 14px above a row
    // of 32px), the strip that moves the window down to the row's end (46px) -- so the page keeps the browser's spacing
    private static let rowMiddle: CGFloat = 30, rowEnd: CGFloat = 46

    private func placeButtons() {
        guard web.band > 0, !window.styleMask.contains(.fullScreen), let close = window.standardWindowButton(.closeButton),
              let mini = window.standardWindowButton(.miniaturizeButton), let zoom = window.standardWindowButton(.zoomButton),
              let bar = close.superview?.superview else { return }
        let h = (2 * Shell.rowMiddle * web.pageZoom).rounded()
        var f = bar.frame
        if f.height != h || f.minY != window.frame.height - h {
            f.size.height = h
            f.origin.y = window.frame.height - h
            bar.frame = f
        }
        for b in [close, mini, zoom] { b.setFrameOrigin(NSPoint(x: b.frame.minX, y: ((h - b.frame.height) / 2).rounded())) }
        web.band = (Shell.rowEnd * web.pageZoom).rounded()
    }

    // for the page (its px): the strip's height, where the window buttons end (right, bottom) and their middle -- nothing in
    // full screen
    private func chrome() -> [String: Double] {
        guard web.band > 0, !window.styleMask.contains(.fullScreen) else { return ["tb": 0, "tl": 0, "ly": 0, "lb": 0] }
        let z = Double(web.pageZoom)
        var tl = 0.0, ly = Double(Shell.rowMiddle) * z
        var lb = ly + 7 * z
        if let b = window.standardWindowButton(.zoomButton), let sv = b.superview {
            let r = sv.convert(b.frame, to: nil)
            tl = Double(r.maxX); ly = Double(window.frame.height - r.midY); lb = Double(window.frame.height - r.minY)
        }
        return ["tb": Double(web.band) / z, "tl": tl / z, "ly": ly / z, "lb": lb / z]
    }

    private func sendChrome() {
        guard let d = try? JSONSerialization.data(withJSONObject: chrome()), let s = String(data: d, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('kontorchrome', {detail: \(s)}))", completionHandler: nil)
    }

    func windowDidEnterFullScreen(_ notification: Notification) { if (notification.object as? NSWindow) === window { sendChrome() } }
    func windowDidExitFullScreen(_ notification: Notification) { if (notification.object as? NSWindow) === window { placeButtons(); sendChrome() } }
    // macOS lays the bar out anew now and then: the buttons back where they belong
    func windowDidResize(_ notification: Notification) { if (notification.object as? NSWindow) === window { placeButtons() } }
    func windowDidBecomeKey(_ notification: Notification) { if (notification.object as? NSWindow) === window { placeButtons() } }
    func windowDidResignKey(_ notification: Notification) { if (notification.object as? NSWindow) === window { placeButtons() } }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { showWindow() }
        return true
    }

    private func activate() {
        if #available(macOS 14.0, *) { NSApp.activate() } else { NSApp.activate(ignoringOtherApps: true) }
    }

    private func showWindow() {
        window.makeKeyAndOrderFront(nil)
        activate()
    }

    // MARK: what may run in here

    private func isHome(_ url: URL?) -> Bool {
        guard let u = url else { return false }
        return u.scheme == home.scheme && u.host == home.host && (u.port ?? 80) == (home.port ?? 80)
    }

    private func isHome(_ origin: WKSecurityOrigin) -> Bool {
        return origin.protocol == home.scheme && origin.host == home.host && origin.port == (home.port ?? 80)
    }

    private func openOutside(_ url: URL) {
        if ["http", "https", "mailto"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
    }

    @objc(webView:decidePolicyForNavigationAction:decisionHandler:)
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = action.request.url
        let mine = isHome(url) || url?.scheme == "blob"
        if action.shouldPerformDownload { decisionHandler(mine ? .download : .cancel); return }          // downloads: Kontor's own only
        if mine || url?.absoluteString == "about:blank" { decisionHandler(.allow); return }
        let main = action.targetFrame?.isMainFrame ?? true
        if let u = url, main, webView === web, u.scheme == "http", u.host == "127.0.0.1" {
            // Kontor on another port (it was changed and Kontor restarted): its address anew from the service, never the browser
            decisionHandler(.cancel)
            var next = kontorAddress()
            if let f = u.fragment, let withPage = URL(string: "#" + f, relativeTo: next)?.absoluteURL { next = withPage }
            home = kontorAddress()
            webView.load(URLRequest(url: next))
            return
        }
        if let u = url, main { openOutside(u) }       // a link out: the browser, never in here
        decisionHandler(.cancel)
    }

    @objc(webView:decidePolicyForNavigationResponse:decisionHandler:)
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let r = response.response as? HTTPURLResponse, let d = r.value(forHTTPHeaderField: "Content-Disposition"), d.lowercased().hasPrefix("attachment") {
            decisionHandler(.download); return
        }
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    // the microphone: Kontor's own page only, its main frame, the microphone only -- then without asking (macOS asks once)
    @objc(webView:requestMediaCapturePermissionForOrigin:initiatedByFrame:type:decisionHandler:)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(frame.isMainFrame && isHome(origin) && isHome(webView.url) && type == .microphone ? .grant : .deny)
    }

    // MARK: loading

    @objc(webView:didFailProvisionalNavigation:withError:)
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let e = error as NSError
        guard webView === web, e.domain == NSURLErrorDomain, [-1001, -1003, -1004, -1005, -1009].contains(e.code) else { return }
        if check != nil { Shell.report("{\"error\": \"\(e.code)\"}", ok: false) }
        // the service is not there (yet, or restarting): a quiet page, then again
        webView.loadHTMLString(Shell.waiting, baseURL: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            guard let s = self else { return }
            s.home = kontorAddress()
            s.web.load(URLRequest(url: s.home))
        }
    }

    @objc(webView:didCommitNavigation:)
    func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
        if webView === web { web.holes = [] }
    }

    @objc(webView:didFinishNavigation:)
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard check != nil, webView === web, isHome(webView.url) else { return }
        // after a message's answer the page's earlier ones (the menu's words, the theme) are through: then what both sides see
        // and the microphone: given without asking (a question would hang until the time is up); a Mac without one says so
        let js = "await window.webkit.messageHandlers.kontor.postMessage({}); let capture = 'stream'; "
            + "try { const m = await Promise.race([navigator.mediaDevices.getUserMedia({audio: true}), new Promise((_, no) => setTimeout(() => no({name: 'timeout'}), 15000))]); "
            + "m.getTracks().forEach(t => t.stop()); } catch (e) { capture = e.name || String(e); } "
            + "return JSON.stringify({capture, title: document.title, "
            + "bridge: !!window.webkit.messageHandlers.kontor, shell: typeof SHELL !== 'undefined' && SHELL, app: typeof APP_MODE !== 'undefined' && APP_MODE, "
            + "agent: navigator.userAgent.indexOf('KontorApp/') >= 0, print: String(window.print).indexOf('postMessage') >= 0, "
            + "badge: String(navigator.setAppBadge).indexOf('postMessage') >= 0})"
        webView.callAsyncJavaScript(js, arguments: [:], in: nil, in: WKContentWorld.page) { [weak self] result in
            guard case .success(let v) = result, let s = v as? String, var d = (try? JSONSerialization.jsonObject(with: Data(s.utf8))) as? [String: Any] else {
                Shell.report("{\"error\": \"no answer\"}", ok: false)
            }
            d["menu"] = NSApp.mainMenu?.items.map { $0.title } ?? []
            d["dark"] = self?.window.appearance?.name == NSAppearance.Name.darkAqua
            d["mic"] = Shell.micState()
            if let s = self { d["chrome"] = ["full": s.web.band > 0, "band": Double(s.web.band), "middle": s.chrome()["ly"] ?? 0] as [String: Any] }
            let items = (NSApp.mainMenu?.items ?? []).flatMap { $0.submenu?.items ?? [] }.flatMap { $0.submenu?.items ?? [$0] }
            let mine = items.filter { $0.action == #selector(Shell.command(_:)) }
            d["commands"] = mine.map { [$0.title, ($0.keyEquivalentModifierMask.contains(.shift) ? "⇧" : "") + $0.keyEquivalent] }
            d["reload"] = items.first { $0.action == #selector(Shell.reload(_:)) }.map { ($0.keyEquivalentModifierMask.contains(.shift) ? "⇧" : "") + $0.keyEquivalent } ?? ""
            if let find = mine.first(where: { $0.representedObject as? String == "find" }) { self?.command(find) }
            webView.evaluateJavaScript("!!document.getElementById('find')") { r, _ in      // (after the command: scripts run in turn)
                d["findBar"] = r as? Bool ?? false
                let out = (try? JSONSerialization.data(withJSONObject: d, options: [.sortedKeys])).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
                Shell.report(out, ok: true)
            }
        }
    }

    @objc(webViewWebContentProcessDidTerminate:)
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if webView === web { webView.load(URLRequest(url: home)) }
    }

    static func report(_ text: String, ok: Bool) -> Never {
        FileHandle.standardOutput.write((text + "\n").data(using: .utf8)!)
        exit(ok ? 0 : 1)
    }

    // MARK: windows the page opens (a receipt, a link out)

    @objc(webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:)
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let u = action.request.url else { return nil }
        guard isHome(u) else { openOutside(u); return nil }
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        let v = WKWebView(frame: NSRect(x: 0, y: 0, width: 900, height: 760), configuration: configuration)
        v.navigationDelegate = self
        v.uiDelegate = self
        w.contentView = v
        w.isReleasedWhenClosed = false
        w.delegate = self
        w.title = "Kontor"
        watches.append(v.observe(\.title, options: [.new]) { [weak w] wv, _ in
            if let t = wv.title, !t.isEmpty { w?.title = t }
        })
        _ = w.cascadeTopLeft(from: NSPoint(x: window.frame.minX + 24, y: window.frame.maxY - 24))
        popups.append(w)
        w.makeKeyAndOrderFront(nil)
        return v
    }

    @objc(webViewDidClose:)
    func webViewDidClose(_ webView: WKWebView) {
        if webView !== web { webView.window?.close() }
    }

    func windowWillClose(_ notification: Notification) {
        if let w = notification.object as? NSWindow, w !== window { popups.removeAll { $0 === w } }
    }

    // MARK: alert, confirm, prompt, choosing files

    private func label(_ key: String) -> String? {
        if let s = labels[key], !s.isEmpty { return s }
        return nil
    }

    private func alert(_ text: String, cancel: Bool) -> NSAlert {
        let a = NSAlert()
        a.messageText = text
        if let ok = label("ok") { a.addButton(withTitle: ok) }
        if cancel, label("ok") != nil, let c = label("cancel") { a.addButton(withTitle: c) }
        return a
    }

    @objc(webView:runJavaScriptAlertPanelWithMessage:initiatedByFrame:completionHandler:)
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        guard let w = webView.window else { completionHandler(); return }
        alert(message, cancel: false).beginSheetModal(for: w) { _ in completionHandler() }
    }

    @objc(webView:runJavaScriptConfirmPanelWithMessage:initiatedByFrame:completionHandler:)
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        guard let w = webView.window else { completionHandler(false); return }
        alert(message, cancel: true).beginSheetModal(for: w) { r in completionHandler(r == .alertFirstButtonReturn) }
    }

    @objc(webView:runJavaScriptTextInputPanelWithPrompt:defaultText:initiatedByFrame:completionHandler:)
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        guard let w = webView.window else { completionHandler(nil); return }
        let a = alert(prompt, cancel: true)
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        field.stringValue = defaultText ?? ""
        a.accessoryView = field
        a.window.initialFirstResponder = field
        a.beginSheetModal(for: w) { r in completionHandler(r == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    @objc(webView:runOpenPanelWithParameters:initiatedByFrame:completionHandler:)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let p = NSOpenPanel()
        p.allowsMultipleSelection = parameters.allowsMultipleSelection
        p.canChooseDirectories = parameters.allowsDirectories
        p.canChooseFiles = true
        guard let w = webView.window else { completionHandler(p.runModal() == .OK ? p.urls : nil); return }
        p.beginSheetModal(for: w) { r in completionHandler(r == .OK ? p.urls : nil) }
    }

    // MARK: downloads -- into the Downloads folder, as Safari does

    @objc(webView:navigationAction:didBecomeDownload:)
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }

    @objc(webView:navigationResponse:didBecomeDownload:)
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first ?? FileManager.default.homeDirectoryForCurrentUser
        var name = suggestedFilename.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ":", with: "-")
        if name.isEmpty || name.hasPrefix(".") { name = "Kontor" + name }
        let base = (name as NSString).deletingPathExtension, ext = (name as NSString).pathExtension
        var dest = dir.appendingPathComponent(name)
        var n = 2
        while FileManager.default.fileExists(atPath: dest.path) {
            dest = dir.appendingPathComponent(ext.isEmpty ? "\(base) \(n)" : "\(base) \(n).\(ext)")
            n += 1
        }
        completionHandler(dest)
    }

    func downloadDidFinish(_ download: WKDownload) {}

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {}

    // MARK: the page talks to the app (Kontor's own page only)

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.frameInfo.isMainFrame, isHome(message.frameInfo.securityOrigin), let body = message.body as? [String: Any] else {
            replyHandler(nil, nil); return
        }
        if let l = body["labels"] as? [String: String] {
            labels = l
            prefs.set(l, forKey: "labels")
            buildMenu()
        }
        if let list = body["commands"] as? [[String: Any]] {       // the page's commands: menu entries with their keys
            let clean = list.compactMap { Shell.parseCommand($0) }
            enabled = Set(clean.filter { $0["on"] as? Bool == true }.compactMap { $0["id"] as? String })
            if Shell.shape(clean) != Shell.shape(commands) {
                commands = clean
                prefs.set(clean, forKey: "commands")
                buildMenu()
            }
        }
        if let t = body["theme"] as? String {             // "auto": like macOS (the page learns the system's mode from this window)
            let look = t == "light" ? NSAppearance(named: .aqua) : t == "dark" ? NSAppearance(named: .darkAqua) : nil
            window.appearance = look
            popups.forEach { $0.appearance = look }
        }
        if body["chrome"] != nil {
            replyHandler(message.webView === web ? chrome() : ["tb": 0, "tl": 0, "ly": 0, "lb": 0], nil); return
        }
        if let h = body["drag"] as? [[Double]], message.webView === web {
            web.holes = h.compactMap { $0.count == 4 ? CGRect(x: $0[0], y: $0[1], width: $0[2], height: $0[3]) : nil }
        }
        if let b = body["badge"] as? NSNumber {
            NSApp.dockTile.badgeLabel = b.intValue > 0 ? String(b.intValue) : nil
        }
        if body["print"] != nil, let v = message.webView {
            printPage(v) { replyHandler(true, nil) }
            return
        }
        if let m = body["mic"] as? String {
            if m == "ask" && AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
                AVCaptureDevice.requestAccess(for: .audio) { _ in DispatchQueue.main.async { replyHandler(Shell.micState(), nil) } }
            } else {
                replyHandler(Shell.micState(), nil)
            }
            return
        }
        replyHandler(true, nil)
    }

    // a command as the page describes it -- only what a menu entry needs, checked: a short name, one key, a known menu
    static func parseCommand(_ c: [String: Any]) -> [String: Any]? {
        guard let id = c["id"] as? String, id.range(of: "^[A-Za-z0-9_]{1,32}$", options: .regularExpression) != nil,
              let menu = c["menu"] as? String, ["file", "find", "view"].contains(menu),
              let key = c["key"] as? String, key.count == 1, let title = c["title"] as? String, !title.isEmpty, title.count <= 80 else { return nil }
        return ["id": id, "menu": menu, "key": key.lowercased(), "title": title, "shift": c["shift"] as? Bool == true, "on": c["on"] as? Bool == true]
    }

    static func shape(_ list: [[String: Any]]) -> String {
        return list.map { c in ["id", "menu", "key", "title"].map { c[$0] as? String ?? "" }.joined(separator: "|") + (c["shift"] as? Bool == true ? "|s" : "") }.joined(separator: "\n")
    }

    static func micState() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return "granted"
        case .notDetermined: return "prompt"
        default: return "denied"
        }
    }

    private func printPage(_ v: WKWebView, done: @escaping () -> Void) {
        guard let w = v.window, printed == nil else { done(); return }
        let info = (NSPrintInfo.shared.copy() as? NSPrintInfo) ?? NSPrintInfo.shared
        info.horizontalPagination = .fit
        info.verticalPagination = .automatic
        let op = v.printOperation(with: info)
        op.showsPrintPanel = true
        op.showsProgressPanel = true
        op.view?.frame = v.bounds
        printed = done
        op.runModal(for: w, delegate: self, didRun: #selector(printDone(_:success:contextInfo:)), contextInfo: nil)
    }

    @objc func printDone(_ op: NSPrintOperation, success: Bool, contextInfo: UnsafeMutableRawPointer?) {
        let d = printed
        printed = nil
        d?()
    }

    // MARK: the menu (its words come from the page)

    private func buildMenu() {
        guard label("quit") != nil else { return }          // until the page has given them: macOS's own menu
        let bar = NSMenu()
        func item(_ key: String, _ action: Selector, _ keyEquivalent: String = "", _ mods: NSEvent.ModifierFlags = .command, mine: Bool = false) -> NSMenuItem {
            let i = NSMenuItem(title: label(key) ?? key, action: action, keyEquivalent: keyEquivalent)
            i.keyEquivalentModifierMask = mods
            if mine { i.target = self }
            return i
        }
        func menu(_ key: String, _ items: [NSMenuItem]) -> NSMenu {
            let m = NSMenu(title: label(key) ?? "Kontor")
            items.forEach { m.addItem($0) }
            let top = NSMenuItem(title: m.title, action: nil, keyEquivalent: "")
            top.submenu = m
            bar.addItem(top)
            return m
        }
        let line = { NSMenuItem.separator() }
        func commandItems(_ menuID: String) -> [NSMenuItem] {
            return commands.filter { $0["menu"] as? String == menuID }.map { c in
                let i = NSMenuItem(title: c["title"] as? String ?? "", action: #selector(command(_:)), keyEquivalent: c["key"] as? String ?? "")
                i.keyEquivalentModifierMask = c["shift"] as? Bool == true ? [.command, .shift] : .command
                i.target = self
                i.representedObject = c["id"] as? String
                return i
            }
        }
        let fileCmds = commandItems("file"), viewCmds = commandItems("view"), findCmds = commandItems("find")
        var findItem: [NSMenuItem] = []
        if !findCmds.isEmpty {
            let f = NSMenu(title: label("find") ?? "")
            findCmds.forEach { f.addItem($0) }
            let i = NSMenuItem(title: f.title, action: nil, keyEquivalent: "")
            i.submenu = f
            findItem = [line(), i]
        }
        _ = menu("app", [item("about", #selector(about(_:)), mine: true), line(),
                         item("settings", #selector(openSettings(_:)), ",", mine: true), line(),
                         item("hide", #selector(NSApplication.hide(_:)), "h"),
                         item("hideOthers", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
                         item("showAll", #selector(NSApplication.unhideAllApplications(_:))), line(),
                         item("quit", #selector(NSApplication.terminate(_:)), "q")])
        _ = menu("file", fileCmds + (fileCmds.isEmpty ? [] : [line()]) + [item("close", #selector(NSWindow.performClose(_:)), "w"), line(),
                          item("print", #selector(printMenu(_:)), "p", mine: true)])
        _ = menu("edit", [item("undo", Selector(("undo:")), "z"), item("redo", Selector(("redo:")), "z", [.command, .shift]), line(),
                          item("cut", #selector(NSText.cut(_:)), "x"), item("copy", #selector(NSText.copy(_:)), "c"),
                          item("paste", #selector(NSText.paste(_:)), "v"), item("selectAll", #selector(NSText.selectAll(_:)), "a")] + findItem)
        _ = menu("view", viewCmds + (viewCmds.isEmpty ? [] : [line()]) + [item("reload", #selector(reload(_:)), "r", mine: true), line(),
                          item("actualSize", #selector(zoomReset(_:)), "0", mine: true),
                          item("zoomIn", #selector(zoomIn(_:)), "+", mine: true),
                          item("zoomOut", #selector(zoomOut(_:)), "-", mine: true), line(),
                          item("fullScreen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control])])
        let win = menu("window", [item("minimize", #selector(NSWindow.performMiniaturize(_:)), "m"), item("zoom", #selector(NSWindow.performZoom(_:)))])
        let help = menu("help", [item("kontorHelp", #selector(openHelp(_:)), "?", mine: true)])
        NSApp.mainMenu = bar
        NSApp.windowsMenu = win
        NSApp.helpMenu = help
    }

    // a command of the page (its menu entry): the page does it, as with its key in a browser
    @objc func command(_ sender: NSMenuItem) {
        guard let id = sender.representedObject as? String, id.range(of: "^[A-Za-z0-9_]{1,32}$", options: .regularExpression) != nil else { return }
        if !window.isVisible { showWindow() }
        web.evaluateJavaScript("typeof kontorCmd === 'function' && kontorCmd('\(id)')", completionHandler: nil)
    }

    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        if menuItem.action == #selector(command(_:)) { return enabled.contains(menuItem.representedObject as? String ?? "") }
        return true
    }

    @objc func about(_ sender: Any?) {
        web.evaluateJavaScript("typeof S !== 'undefined' && S.STATUS ? String(S.STATUS.version || '') : ''") { r, _ in
            var o: [NSApplication.AboutPanelOptionKey: Any] = [:]
            if let v = r as? String, !v.isEmpty { o[.applicationVersion] = v; o[.version] = "" }
            NSApp.orderFrontStandardAboutPanel(options: o)
            self.activate()
        }
    }

    private func goTo(_ hash: String) {
        showWindow()
        web.evaluateJavaScript("typeof go === 'function' ? go('\(hash)') : (location.hash = '\(hash)')", completionHandler: nil)
    }

    @objc func openSettings(_ sender: Any?) { goTo("#settings") }
    @objc func openHelp(_ sender: Any?) { goTo("#help") }
    @objc func printMenu(_ sender: Any?) { web.evaluateJavaScript("window.print()", completionHandler: nil) }

    @objc func reload(_ sender: Any?) {
        if isHome(web.url) { web.reload() } else { home = kontorAddress(); web.load(URLRequest(url: home)) }
    }

    private func zoom(_ z: CGFloat) {
        web.pageZoom = min(3, max(0.5, z))
        prefs.set(Double(web.pageZoom), forKey: "zoom")
        placeButtons()
        sendChrome()
    }

    @objc func zoomIn(_ sender: Any?) { zoom(web.pageZoom * 1.1) }
    @objc func zoomOut(_ sender: Any?) { zoom(web.pageZoom / 1.1) }
    @objc func zoomReset(_ sender: Any?) { zoom(1) }

    // MARK: in the page

    // the page's print goes to macOS's print dialog (with the page's own before/after print steps); the badge to the Dock
    static let bridge = """
    (() => {
      const k = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.kontor; if (!k) return;
      window.print = () => { window.dispatchEvent(new Event('beforeprint')); k.postMessage({print: 1}).catch(() => {}).then(() => window.dispatchEvent(new Event('afterprint'))); };
      navigator.setAppBadge = n => k.postMessage({badge: Number(n) || 0}).then(() => undefined);
      navigator.clearAppBadge = () => k.postMessage({badge: 0}).then(() => undefined);
    })();
    """

    // while the service is not there: an empty page that turns (no words: nothing to translate)
    static let waiting = "<!doctype html><meta name=color-scheme content='light dark'><style>html,body{height:100%;margin:0;display:grid;place-items:center;"
        + "background:Canvas}i{width:22px;height:22px;border:2.5px solid rgba(128,128,128,.35);border-top-color:CanvasText;border-radius:50%;"
        + "animation:s .9s linear infinite}@keyframes s{to{transform:rotate(360deg)}}</style><i></i>"
}

let args = CommandLine.arguments
let check: String? = args.firstIndex(of: "--check").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
let app = NSApplication.shared
let shell = Shell(check: check)
app.delegate = shell
app.setActivationPolicy(check == nil ? .regular : .accessory)
app.run()
