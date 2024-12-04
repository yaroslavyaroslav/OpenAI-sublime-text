from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Tuple

from .cacher import Cacher

logger = logging.getLogger(__name__)


class MessageCreator:
    @classmethod
    def create_message(
        cls,
        cacher: Cacher,
        selected_text: List[Tuple[str, str | None, str]] | None = None,
        command: str | None = None,
        tool_call_id: str | None = None,
    ) -> List[Dict[str, str]]:
        messages = cacher.read_all()
        logger.debug(len(selected_text) if selected_text else None)
        if selected_text:
            new_messages = [
                {
                    'role': 'user',
                    **({'file_path': file_path} if file_path is not None else {}),
                    **({'scope_name': scope} if scope is not None else {}),
                    'content': text,  # Content
                    'name': 'OpenAI_completion',
                }
                for scope, file_path, text in selected_text  # Iterates over provided non-None selected_text
            ]

            logger.debug(['content' in message for message in new_messages])
            messages.extend(new_messages)

        if command:
            if tool_call_id:
                messages.append(
                    {
                        'role': 'tool',
                        'content': command,
                        'tool_call_id': tool_call_id,
                        'name': 'OpenAI_completion',
                    }
                )
            else:
                messages.append({'role': 'user', 'content': command, 'name': 'OpenAI_completion'})

        logger.debug(['content' in message for message in messages])
        return messages

    @classmethod
    def create_image_message(
        cls, cacher: Cacher, image_url: str | None, command: str | None
    ) -> List[Dict[str, Any]]:
        """Create a message with a list of image URLs (in base64) and a command."""
        messages = cacher.read_all()

        # Split single image_urls_string by newline into multiple paths
        if image_url:
            image_urls = image_url.split('\n')
            image_data_list = []

            for image_url in image_urls:
                image_url = image_url.strip()
                if image_url:  # Only handle non-empty lines
                    base64_image = MessageCreator.encode_image(image_url)
                    image_data_list.append(
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:image/jpeg;base64,{base64_image}'},
                        }
                    )

            messages.append(
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': command},  # type: ignore
                        *image_data_list,  # Add all the image data
                    ],
                    'name': 'OpenAI_completion',
                }
            )

        return messages

    @classmethod
    def create_image_fake_message(
        cls, _: Cacher, image_url: str | None, command: str | None
    ) -> List[Dict[str, str]]:
        messages = []
        if image_url:
            messages.append({'role': 'user', 'content': command, 'name': 'OpenAI_completion'})
        if image_url:
            messages.append({'role': 'user', 'content': image_url, 'name': 'OpenAI_completion'})
        return messages

    @classmethod
    def encode_image(cls, image_path: str) -> str:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    @classmethod
    def calculate_completion_tokens(cls, responses: List[Dict[str, str]]) -> int:
        total_tokens = 0
        for response in responses:
            if response['content'] and response['role'] == 'assistant':
                total_tokens += int(len(response['content']) / 4)
        return total_tokens
