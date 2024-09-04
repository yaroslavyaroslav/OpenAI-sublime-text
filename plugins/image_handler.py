import os
import re
from urllib.parse import urlparse
import sublime
import logging

logger = logging.getLogger(__name__)


class ImageValidator:
    @staticmethod
    def get_valid_image_input(text: str) -> str:
        """Check if the input text contains valid image URLs or file paths; return the original string if valid."""
        clipboard_content = (
            sublime.get_clipboard().strip() if sublime.get_clipboard() else text.strip()
        )

        # Split the content by spaces or newlines
        potential_images = re.split(r'\n', clipboard_content)

        logger.debug('potential_images count: %s', len(potential_images))

        # Check if all parts are valid image paths (URLs or local files)
        all_valid = all(
            ImageValidator.is_local_image(image) or ImageValidator.is_valid_url(image)
            for image in potential_images
            if image  # Only check non-empty strings
        )

        if all_valid:
            logger.debug('Returning original valid image input string.')
            return clipboard_content  # If all are valid image refs, return the original text

        logger.debug('Invalid images found; returning fallback.')
        return text  # If not valid, fallback to the text that was passed in

    @staticmethod
    def is_valid_url(text: str) -> bool:
        """Check if the text is a valid URL pointing to an image."""
        try:
            result = urlparse(text)
            # Ensure the URL scheme is HTTP/HTTPS and it has a valid image extension
            return all(
                [result.scheme in ('http', 'https'), result.netloc]
            ) and re.match(r'.*\.(jpg|jpeg|png)$', text)
        except:
            return False

    @staticmethod
    def is_local_image(text: str) -> bool:
        """Check if the text is a valid local file path pointing to an image."""
        return os.path.isfile(text) and re.match(r'.*\.(jpg|jpeg|png)$', text)
