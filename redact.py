"""
Image-level PII redaction using Apple Vision OCR.

Runs OCR on a screenshot, detects PII via regex patterns, and draws
black rectangles over the PII regions before anything else sees the image.

This is the first line of defense. The text-level sanitize_text() in
core.py is the second -- it catches anything the OCR missed.
"""

import re
import logging
from typing import Optional

log = logging.getLogger("shutter.redact")

# ---------------------------------------------------------------------------
# PII PATTERNS — applied at the image level
#
# These are high-confidence patterns that should always be redacted.
# Aggressive patterns (long tokens, file paths) stay in core.sanitize_text()
# to avoid false positives on variable names and UI labels.
# ---------------------------------------------------------------------------

PII_PATTERNS = [
    # Credit cards (4 groups of 4 digits, optional separators)
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), "credit_card"),

    # Social Security Numbers (XXX-XX-XXXX)
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "ssn"),

    # Email addresses
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'), "email"),

    # UUIDs
    (re.compile(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        re.IGNORECASE,
    ), "uuid"),

    # US phone numbers: (555) 123-4567, 555-123-4567, +1-555-123-4567
    (re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), "phone"),

    # IPv4 addresses
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "ipv4"),

    # IPv6 addresses (common full format)
    (re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'), "ipv6"),

    # MAC addresses (AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF)
    (re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'), "mac_address"),

    # Cryptocurrency wallets (Bitcoin legacy, bech32, Ethereum)
    (re.compile(
        r'\b(?:0x[0-9a-fA-F]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{25,90})\b'
    ), "crypto_wallet"),

    # URLs containing auth tokens or secret query params
    (re.compile(
        r'https?://\S+[?&](?:token|key|secret|auth|api_key|access_token|password)=\S+',
        re.IGNORECASE,
    ), "url_with_secret"),

    # Credential keyword=value pairs
    (re.compile(
        r'(?:key|token|secret|password|api_key|bearer|auth|credential|'
        r'private_key|access_token|refresh_token|apikey|api[_\-]secret)\s*[=:]\s*\S+',
        re.IGNORECASE,
    ), "credential"),
]


# ---------------------------------------------------------------------------
# OCR — Apple Vision framework via PyObjC
# ---------------------------------------------------------------------------

def _ocr_image(image_path: str) -> list[dict]:
    """
    Run Apple Vision OCR on an image file.

    Returns list of dicts with text, the observation object, the
    recognized text candidate, and confidence score.
    """
    import Vision
    import Quartz
    from Foundation import NSURL

    input_url = NSURL.fileURLWithPath_(image_path)
    input_image = Quartz.CIImage.imageWithContentsOfURL_(input_url)

    if input_image is None:
        log.warning("Could not load image for OCR: %s", image_path)
        return []

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(1)  # 1 = accurate
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
        input_image, None
    )

    success = handler.performRequests_error_([request], None)
    if not success[0]:
        log.warning("OCR request failed: %s", success[1])
        return []

    results = []
    for observation in (request.results() or []):
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        results.append({
            "text": str(candidate.string()),
            "observation": observation,
            "candidate": candidate,
            "confidence": float(candidate.confidence()),
        })

    return results


# ---------------------------------------------------------------------------
# PII REGION DETECTION
# ---------------------------------------------------------------------------

def _find_pii_regions(ocr_results: list[dict], image_width: int, image_height: int) -> list[tuple]:
    """
    Find PII in OCR results and return pixel-coordinate bounding boxes.

    Returns list of (x1, y1, x2, y2) tuples in pixel coordinates
    (top-left origin, suitable for PIL).
    """
    from Foundation import NSRange

    regions = []

    for result in ocr_results:
        text = result["text"]
        candidate = result["candidate"]
        observation = result["observation"]

        for pattern, label in PII_PATTERNS:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - match.start()

                # Try character-level bounding box for precision
                ns_range = NSRange(start, length)
                box_result = candidate.boundingBoxForRange_error_(ns_range, None)

                if box_result and box_result[0]:
                    bbox = box_result[0].boundingBox()
                else:
                    # Fallback: use the whole observation's bounding box
                    log.debug("Falling back to observation bbox for %s", label)
                    bbox = observation.boundingBox()

                # Convert normalized (0-1) coords to pixel coords.
                # Vision uses bottom-left origin; PIL uses top-left.
                x = bbox.origin.x * image_width
                y_bottom = bbox.origin.y * image_height
                w = bbox.size.width * image_width
                h = bbox.size.height * image_height

                # Flip Y axis for PIL (top-left origin)
                y_top = image_height - y_bottom - h

                # Add 2px padding for full coverage
                x1 = max(0, x - 2)
                y1 = max(0, y_top - 2)
                x2 = min(image_width, x + w + 2)
                y2 = min(image_height, y_top + h + 2)

                regions.append((x1, y1, x2, y2))
                log.debug("PII [%s] at (%.0f,%.0f)-(%.0f,%.0f)", label, x1, y1, x2, y2)

    return regions


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def redact_image(image_path: str) -> str:
    """
    Redact PII from a screenshot image.

    Runs Apple Vision OCR to find text, matches PII patterns,
    and draws black rectangles over detected PII regions.

    Args:
        image_path: Path to the PNG screenshot.

    Returns:
        Path to the redacted image (modified in-place),
        or the original path unchanged if no PII was found or OCR failed.
    """
    from PIL import Image, ImageDraw

    try:
        ocr_results = _ocr_image(image_path)
        if not ocr_results:
            log.debug("No text found by OCR, skipping redaction")
            return image_path

        img = Image.open(image_path)
        image_width, image_height = img.size

        regions = _find_pii_regions(ocr_results, image_width, image_height)
        if not regions:
            log.debug("No PII detected in OCR text")
            img.close()
            return image_path

        draw = ImageDraw.Draw(img)
        for (x1, y1, x2, y2) in regions:
            draw.rectangle([(x1, y1), (x2, y2)], fill="black")

        img.save(image_path)
        img.close()
        log.info("Redacted %d PII region(s) from screenshot", len(regions))
        return image_path

    except Exception as e:
        log.error("Image redaction failed: %s", e)
        # On failure, return the original path.
        # Text-level sanitize_text() is the fallback defense.
        return image_path
