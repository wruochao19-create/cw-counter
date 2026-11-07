# OCR model provenance

The runtime uses RapidOCR 1.4.4 (Apache-2.0) and CPU ONNX Runtime 1.23.2 (MIT).
Package licenses remain in `.deps` alongside the installed distributions.

- Project: https://github.com/RapidAI/RapidOCR
- English recognition model: `en-rec.onnx`, 8,967,018 bytes.
- Download source: https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/en_PP-OCRv3_rec_infer.onnx
- SHA-256: `ef7abd8bd3629ae57ea2c28b425c1bd258a871b93fd2fe7c433946ade9b5d9ea`
- Detection model: RapidOCR wheel's `ch_PP-OCRv4_det_infer.onnx` (generic text detection, English recognition uses the separate model above).
- No network access is performed by the running application. All model paths refer to local files.

The package also contains its default recognizer, but this application explicitly selects the English model.
No screenshots are sent to a server. The OCR engine is shared across calibration and counting.
