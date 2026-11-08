"""Use signed-in local Ollama, or an API key for direct cloud access."""
import os
from urllib.parse import urlparse


def base_url():
    return os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')


def configured():
    return (urlparse(base_url()).hostname in {'localhost', '127.0.0.1', '::1'}
            or bool(os.getenv('OLLAMA_API_KEY')))


def chat_headers():
    key = os.getenv('OLLAMA_API_KEY', '')
    return {'Authorization': f'Bearer {key}'} if key else {}
