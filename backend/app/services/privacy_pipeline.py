import pytesseract
from PIL import Image
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from typing import Tuple, List, Dict
from io import BytesIO
import logging

logger = logging.getLogger(__name__)


class PrivacyPipeline:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self._add_custom_recognizers()

    def _add_custom_recognizers(self):
        from presidio_analyzer import Pattern, PatternRecognizer

        aws_key_pattern = Pattern(
            name="aws_access_key",
            regex=r"(?i)(AKIA[0-9A-Z]{16})",
            score=0.95,
        )
        aws_key_recognizer = PatternRecognizer(
            supported_entity="AWS_ACCESS_KEY",
            patterns=[aws_key_pattern],
        )
        self.analyzer.registry.add_recognizer(aws_key_recognizer)

        gcp_key_pattern = Pattern(
            name="gcp_service_account",
            regex=r'"private_key_id":\s*"[a-f0-9]{40}"',
            score=0.9,
        )
        gcp_key_recognizer = PatternRecognizer(
            supported_entity="GCP_SERVICE_KEY",
            patterns=[gcp_key_pattern],
        )
        self.analyzer.registry.add_recognizer(gcp_key_recognizer)

        generic_api_key_pattern = Pattern(
            name="generic_api_key",
            regex=r'(?i)(api[_-]?key|apikey|secret[_-]?key|access[_-]?token)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            score=0.85,
        )
        generic_api_key_recognizer = PatternRecognizer(
            supported_entity="API_KEY",
            patterns=[generic_api_key_pattern],
        )
        self.analyzer.registry.add_recognizer(generic_api_key_recognizer)

        hostname_pattern = Pattern(
            name="internal_hostname",
            regex=r'(?i)([a-z0-9-]+\.(internal|local|corp|private|intranet))',
            score=0.7,
        )
        hostname_recognizer = PatternRecognizer(
            supported_entity="INTERNAL_HOSTNAME",
            patterns=[hostname_pattern],
        )
        self.analyzer.registry.add_recognizer(hostname_recognizer)

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        return text

    def analyze_text(self, text: str) -> List[Dict]:
        results = self.analyzer.analyze(
            text=text,
            entities=[
                "PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "CREDIT_CARD",
                "IP_ADDRESS",
                "PERSON",
                "AWS_ACCESS_KEY",
                "GCP_SERVICE_KEY",
                "API_KEY",
                "INTERNAL_HOSTNAME",
            ],
            language="en",
        )
        return [
            {
                "entity_type": result.entity_type,
                "start": result.start,
                "end": result.end,
                "score": result.score,
            }
            for result in results
        ]

    def redact_text(self, text: str) -> Tuple[str, List[Dict]]:
        results = self.analyzer.analyze(
            text=text,
            entities=[
                "PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "CREDIT_CARD",
                "IP_ADDRESS",
                "PERSON",
                "AWS_ACCESS_KEY",
                "GCP_SERVICE_KEY",
                "API_KEY",
                "INTERNAL_HOSTNAME",
            ],
            language="en",
        )

        operators = {
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CARD]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP]"}),
            "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
            "AWS_ACCESS_KEY": OperatorConfig("replace", {"new_value": "[AWS_KEY]"}),
            "GCP_SERVICE_KEY": OperatorConfig("replace", {"new_value": "[GCP_KEY]"}),
            "API_KEY": OperatorConfig("replace", {"new_value": "[API_KEY]"}),
            "INTERNAL_HOSTNAME": OperatorConfig("replace", {"new_value": "[HOSTNAME]"}),
        }

        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        bounding_boxes = [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": r.score,
            }
            for r in results
        ]

        return anonymized.text, bounding_boxes

    def sanitize_image(self, image_bytes: bytes, bounding_boxes: List[Dict]) -> bytes:
        image = Image.open(BytesIO(image_bytes))
        draw = None

        try:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(image)
        except ImportError:
            logger.warning("ImageDraw not available, returning original image")
            return image_bytes

        img_width, img_height = image.size

        for box in bounding_boxes:
            try:
                text_in_image = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT
                )
                for i, text in enumerate(text_in_image["text"]):
                    if text and any(
                        keyword in text.upper()
                        for keyword in ["KEY", "SECRET", "TOKEN", "PASSWORD", "API"]
                    ):
                        x = text_in_image["left"][i]
                        y = text_in_image["top"][i]
                        w = text_in_image["width"][i]
                        h = text_in_image["height"][i]
                        draw.rectangle(
                            [x, y, x + w, y + h], fill="black"
                        )
            except Exception as e:
                logger.error(f"Error processing bounding box: {e}")

        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def process_screen_capture(self, image_bytes: bytes) -> Tuple[str, bytes]:
        raw_text = self.extract_text_from_image(image_bytes)
        redacted_text, bounding_boxes = self.redact_text(raw_text)
        sanitized_image = self.sanitize_image(image_bytes, bounding_boxes)

        return redacted_text, sanitized_image
