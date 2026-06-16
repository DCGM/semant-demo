# Task - text quality
- Assess the text quality and usability of `Text to be classified`.

# Classes
- `clean` — text is well-formed, fluent, and consistently readable with minimal or no OCR errors; meaning is fully preserved
- `minor_errors` — text has occasional OCR artifacts, spelling errors, or garbled characters, but the main meaning and structure are clearly preserved
- `noisy` — text has frequent OCR errors, missing words, or corrupted passages, but the general content is still largely recoverable
- `heavily_degraded` — text has severe corruption, systematic OCR failure, or major gaps; some information may be recoverable but reliability is low
- `unreadable` — text is so corrupted, fragmented, or structurally broken that reliable content extraction is not possible
