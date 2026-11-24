// The text of a receipt for Kontor (receipt_text.py): the file comes on stdin -- a PDF or a picture -- and its text goes to stdout
// as JSON {"text", "how"}. Recognized on this Mac only: the text layer of a PDF (PDFKit), otherwise Apple's text recognition
// (Vision) on each page or the picture. No network, no files: it runs in the macOS sandbox Kontor gives it and ends.
//
// Started with the word "layout": every page with its words and where they stand, for tables (pdf_tables.py) -- JSON
// {"pages": [{"n", "w", "h", "how", "items": [[x, y, width, height, text] ...]}], "count", "cut"}, all in tenths of a point,
// y counted from the top of the page.
//
// Started with the word "pictures": every page of a PDF as the language model is shown it -- upright as it is shown, about
// 1600 pixels on its longer side, as JPEG -- JSON {"pages": [{"n", "jpeg": base64}], "count", "cut"}.
import CoreGraphics
import Foundation
import ImageIO
import PDFKit
import Vision

let maxPages = 10
let maxChars = 20000
let maxLayoutPages = 300          // "layout": pages read at most ...
let maxRecognizedPages = 40       // ... of them scanned ones (text recognition takes its time)
let maxItems = 250000             // ... and words in all
let maxPicturePages = 60          // "pictures": pages drawn at most ...
let pictureSide: CGFloat = 1600   // ... each this many pixels on its longer side

func fail(_ why: String) -> Never {
    // the text recognition did not work (in the sandbox, say): said so -- Kontor reports it, it does not mean "no text"
    FileHandle.standardError.write(why.data(using: .utf8) ?? Data())
    exit(2)
}

func recognize(_ image: CGImage) -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["de-DE", "en-US"]
    do {
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    } catch {
        fail("vision: \(error.localizedDescription)")
    }
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

func render(_ page: PDFPage) -> CGImage? {
    // a scanned page: drawn at twice its size (sharper text), never larger than about 40 million pixels
    let box = page.bounds(for: .mediaBox)
    let scale: CGFloat = 2
    let width = Int(box.width * scale), height = Int(box.height * scale)
    guard width > 0, height > 0, width * height < 40_000_000,
          let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    return ctx.makeImage()
}

func flatten(_ image: CGImage) -> CGImage {
    // a picture with transparent parts (a PNG, a page saved as a picture): on white, as on paper -- text recognition sees
    // transparent pixels as black, and black text on them would be gone
    let w = image.width, h = image.height
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return image }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage() ?? image
}

func tenths(_ v: CGFloat) -> Int {
    let x = (v * 10).rounded()
    return x.isFinite ? Int(max(-1_000_000, min(1_000_000, x))) : 0
}

func shown(_ page: PDFPage) -> (CGFloat, CGFloat, CGAffineTransform) {
    // the page as it is shown: its size (turned pages the other way round) and the way from its own space to that
    let box = page.bounds(for: .cropBox)
    let turned = (page.rotation / 90) % 2 != 0
    return (turned ? box.height : box.width, turned ? box.width : box.height, page.transform(for: .cropBox))
}

func layerWords(_ page: PDFPage, _ text: NSString, _ height: CGFloat, _ turn: CGAffineTransform, _ skipBreaks: Bool) -> ([[Any]], Int) {
    // the words of the page's own text, each with its place: letters up to a blank or a jump (a new line, a new column) --
    // and how often a word broke off onto another line or backwards (letters and places do not go together then)
    let places = page.numberOfCharacters
    let count = text.length
    var out: [[Any]] = []
    var jumps = 0
    var start = -1
    var rect = CGRect.null
    var place = 0                                        // the place that belongs to the letter at i
    var tall: CGFloat = 0                                // the highest letter of the line so far (a word of small letters is not small writing)
    var i = 0
    while i <= count {
        var ends = i == count
        var bounds = CGRect.null
        if !ends {
            let c = text.character(at: i)
            let lineEnd = c == 10 || c == 13
            if lineEnd { tall = 0 }
            if lineEnd && skipBreaks {
                ends = true                              // (a line end PDFKit put into the string: it has no place)
            } else {
                let at = place
                place += 1
                if lineEnd || c == 32 || c == 9 || c == 0xA0 || c == 0x2028 || c == 0x2029 || c == 0x3000 {
                    ends = true
                } else if at < places {
                    let r = page.characterBounds(at: at).applying(turn)
                    if r.width > 0 && r.height > 0 && r.origin.x.isFinite && r.origin.y.isFinite {
                        bounds = r
                        if start >= 0 && !rect.isNull {
                            let h = max(r.height, rect.height, tall)
                            let away = abs(r.midY - rect.midY) > h * 0.75 || r.maxX < rect.minX - h * 0.5
                            if away || r.minX - rect.maxX > h * 0.18 {
                                ends = true              // no blank, but apart from the word so far (a gap, another line): a word of its own
                                if away { jumps += 1 }
                            }
                        }
                    }
                }
            }
        }
        if ends {
            if start >= 0 && !rect.isNull {
                let word = text.substring(with: NSRange(location: start, length: i - start)).trimmingCharacters(in: .whitespacesAndNewlines)
                if !word.isEmpty {
                    let item: [Any] = [tenths(rect.minX), tenths(height - rect.maxY), tenths(rect.width), tenths(rect.height), String(word.prefix(200))]
                    out.append(item)
                }
            }
            start = -1
            rect = CGRect.null
        }
        if !bounds.isNull {
            if start < 0 { start = i }
            rect = rect.isNull ? bounds : rect.union(bounds)
            tall = max(tall, bounds.height)
        } else if !ends && start < 0 {
            start = i                                    // a letter without a place of its own: part of the word that follows
        }
        i += 1
    }
    return (out, jumps)
}

func layerItems(_ page: PDFPage) -> ([[Any]], [Int]) {
    // PDFKit's string of a page holds line ends that its places of the letters do not count (the place of letter i is then
    // i less the line ends before it) -- or, should that differ on another system, does count them: read both ways, the one
    // whose words stay in a row is the page's. With it: length of the string, places, line ends, jumps counted either way
    guard let string = page.string else { return ([], []) }
    let text = string as NSString
    let (_, height, turn) = shown(page)
    var breaks = 0
    for i in 0..<text.length {
        let c = text.character(at: i)
        if c == 10 || c == 13 { breaks += 1 }
    }
    let counted = layerWords(page, text, height, turn, false)
    if breaks == 0 { return (counted.0, [text.length, page.numberOfCharacters, 0, counted.1, counted.1]) }
    let skipped = layerWords(page, text, height, turn, true)
    let take = skipped.1 < counted.1 || (skipped.1 == counted.1 && page.numberOfCharacters < text.length)
    return (take ? skipped.0 : counted.0, [text.length, page.numberOfCharacters, breaks, counted.1, skipped.1])
}

func recognizedItems(_ image: CGImage, _ width: CGFloat, _ height: CGFloat) -> [[Any]] {
    // the words Apple's text recognition finds, each with its place on the page (or the place of its line)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["de-DE", "en-US"]
    do {
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    } catch {
        fail("vision: \(error.localizedDescription)")
    }
    var out: [[Any]] = []
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let s = candidate.string
        let line = observation.boundingBox
        let letters = CGFloat(max(1, s.count))
        var i = s.startIndex
        while i < s.endIndex {
            if s[i] == " " {
                i = s.index(after: i)
                continue
            }
            var j = i
            while j < s.endIndex && s[j] != " " { j = s.index(after: j) }
            // the word's own place; where Vision does not give one: its share of the line, by its letters (never the whole line
            // for every word -- words of two columns would lie on top of each other)
            let first = CGFloat(s.distance(from: s.startIndex, to: i)), behind = CGFloat(s.distance(from: s.startIndex, to: j))
            var box = CGRect(x: line.minX + line.width * first / letters, y: line.minY, width: line.width * (behind - first) / letters, height: line.height)
            if let part = try? candidate.boundingBox(for: i..<j) { box = part.boundingBox }
            let item: [Any] = [tenths(box.minX * width), tenths((1 - box.maxY) * height), tenths(box.width * width), tenths(box.height * height),
                               String(s[i..<j].prefix(200))]
            out.append(item)
            i = j
        }
    }
    return out
}

func jpeg(_ image: CGImage) -> Data? {
    let out = NSMutableData()
    guard let dest = CGImageDestinationCreateWithData(out as CFMutableData, "public.jpeg" as CFString, 1, nil) else { return nil }
    CGImageDestinationAddImage(dest, image, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
    return CGImageDestinationFinalize(dest) ? out as Data : nil
}

func pagePicture(_ page: PDFPage) -> Data? {
    // a page as it is shown (a turned page upright): drawn on white into a picture of its shown size, scaled to pictureSide on
    // its longer side -- PDFKit's draw(with:to:) itself turns the page and places its box
    let (width, height, _) = shown(page)
    let longest = max(width, height)
    guard longest > 0 else { return nil }
    let scale = min(pictureSide / longest, 4)
    let w = Int((width * scale).rounded()), h = Int((height * scale).rounded())
    guard w > 0, h > 0, let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                            bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .cropBox, to: ctx)
    guard let image = ctx.makeImage() else { return nil }
    return jpeg(image)
}

func pictures(_ data: Data) -> [String: Any] {
    guard data.starts(with: [0x25, 0x50, 0x44, 0x46]), let doc = PDFDocument(data: data) else { return ["pages": [], "count": 0, "cut": false] }
    var pages: [[String: Any]] = []
    for i in 0..<min(doc.pageCount, maxPicturePages) {
        guard let page = doc.page(at: i), let picture = pagePicture(page) else { continue }
        pages.append(["n": i + 1, "jpeg": picture.base64EncodedString()])
    }
    return ["pages": pages, "count": doc.pageCount, "cut": doc.pageCount > maxPicturePages]
}

func layout(_ data: Data) -> [String: Any] {
    var pages: [[String: Any]] = []
    var count = 0
    var cut = false
    var items = 0
    var recognized = 0
    if data.starts(with: [0x25, 0x50, 0x44, 0x46]) {           // "%PDF"
        guard let doc = PDFDocument(data: data) else { return ["pages": pages, "count": 0, "cut": false] }
        count = doc.pageCount
        cut = count > maxLayoutPages
        for i in 0..<min(count, maxLayoutPages) {
            guard let page = doc.page(at: i) else { continue }
            var (width, height, _) = shown(page)
            var how = "pdf"
            var (list, letters) = layerItems(page)
            if list.count < 12 {
                // hardly any text of its own: a scan (with a stamp or a file number as its only text), or a page that says
                // little. Read from its picture too -- what finds clearly more words counts
                let own = list.count
                if own < 3 { how = "none" }
                if recognized >= maxRecognizedPages {
                    if own < 3 { cut = true }
                } else if let image = render(page) {
                    let box = page.bounds(for: .mediaBox)
                    let seen = recognizedItems(image, box.width, box.height)
                    recognized += 1
                    if seen.count > own * 2 + 5 || (own < 3 && seen.count > 0) {
                        list = seen
                        width = box.width
                        height = box.height
                        how = "ocr"
                    }
                }
            }
            items += list.count
            if items > maxItems {
                cut = true
                break
            }
            if how != "pdf" { letters = [] }
            pages.append(["n": i + 1, "w": tenths(width), "h": tenths(height), "how": how, "items": list, "letters": letters])
        }
    } else if let source = CGImageSourceCreateWithData(data as CFData, nil) {
        let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                     kCGImageSourceThumbnailMaxPixelSize: 6000, kCGImageSourceShouldCacheImmediately: false]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, opts as CFDictionary) else { fail("picture not readable") }
        let width = CGFloat(image.width), height = CGFloat(image.height)
        count = 1
        pages.append(["n": 1, "w": tenths(width), "h": tenths(height), "how": "ocr", "items": recognizedItems(flatten(image), width, height)])
    }
    return ["pages": pages, "count": count, "cut": cut]
}

let data = FileHandle.standardInput.readDataToEndOfFile()
if CommandLine.arguments.dropFirst().contains("layout") {
    if let json = try? JSONSerialization.data(withJSONObject: layout(data)) {
        FileHandle.standardOutput.write(json)
    }
    exit(0)
}
if CommandLine.arguments.dropFirst().contains("pictures") {
    if let json = try? JSONSerialization.data(withJSONObject: pictures(data)) {
        FileHandle.standardOutput.write(json)
    }
    exit(0)
}
var parts: [String] = []
var how = "none"
if data.starts(with: [0x25, 0x50, 0x44, 0x46]) {           // "%PDF"
    if let doc = PDFDocument(data: data) {
        for i in 0..<min(doc.pageCount, maxPages) {
            guard let page = doc.page(at: i) else { continue }
            let layer = (page.string ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if layer.count >= 20 {
                parts.append(layer)
                if how == "none" { how = "pdf" }
            } else if let image = render(page) {
                parts.append(recognize(image))
                how = "ocr"
            }
        }
    }
} else if let source = CGImageSourceCreateWithData(data as CFData, nil) {
    // a picture: turned as it was taken (a phone photo), at most 6000 pixels on its longer side -- however many it has, the
    // memory it takes stays bounded
    let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                 kCGImageSourceThumbnailMaxPixelSize: 6000, kCGImageSourceShouldCacheImmediately: false]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, opts as CFDictionary) else { fail("picture not readable") }
    parts.append(recognize(flatten(image)))
    how = "ocr"
}
let text = String(parts.joined(separator: "\n\n").prefix(maxChars))
if let json = try? JSONSerialization.data(withJSONObject: ["text": text, "how": how]) {
    FileHandle.standardOutput.write(json)
}
