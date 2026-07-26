from __future__ import annotations

from typing import Any

from .base import BaseTool


class MockWikipediaTool(BaseTool):
    ARTICLES = {
        "Python (programming language)": {
            "title": "Python (programming language)",
            "summary": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.",
            "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        },
        "Artificial intelligence": {
            "title": "Artificial intelligence",
            "summary": "Artificial intelligence (AI) is the intelligence of machines or software, as opposed to the intelligence of humans or animals.",
            "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
        },
        "Machine learning": {
            "title": "Machine learning",
            "summary": "Machine learning is a field of study in artificial intelligence concerned with the development and study of statistical algorithms that can learn from data and generalize to unseen data.",
            "url": "https://en.wikipedia.org/wiki/Machine_learning",
        },
    }

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        query = input_data.get("query", "Python (programming language)")
        article = self.ARTICLES.get(query, self.ARTICLES["Python (programming language)"])
        return article