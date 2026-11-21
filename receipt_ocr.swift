// The text of a receipt for Kontor (receipt_text.py): the file comes on stdin -- a PDF or a picture -- and its text goes to stdout
// as JSON {"text", "how"}. Recognized on this Mac only: the text layer of a PDF (PDFKit), otherwise Apple's text recognition
// (Vision) on each page or the picture. No network, no files: it runs in the macOS sandbox Kontor gives it and ends.
import CoreGraphics
import Foundation
import ImageIO
import PDFKit
import Vision

let maxPages = 10
let maxChars = 20000

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

let data = FileHandle.standardInput.readDataToEndOfFile()
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
