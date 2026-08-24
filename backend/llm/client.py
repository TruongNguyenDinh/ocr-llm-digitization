import requests


class QwenClient:
    def __init__(
        self,
        model="qwen3:8b",
        base_url="http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url

    def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                },
            },
            timeout=300,
        )

        response.raise_for_status()

        return response.json()["response"]