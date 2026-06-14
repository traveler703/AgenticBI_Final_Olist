"""订单评论文本 NLP：清洗、关键词、情感（葡英文规则）、词云数据。"""
from __future__ import annotations

import re
from collections import Counter

import pandas as pd

from datastore.olist_db import read_df

POSITIVE_WORDS = {
    "bom", "boa", "excelente", "otimo", "ótimo", "perfeito", "perfeita", "rapido", "rápido",
    "adorei", "gostei", "recomendo", "satisfeito", "satisfeita", "qualidade", "correto", "correta",
}
NEGATIVE_WORDS = {
    "ruim", "péssimo", "pessimo", "atraso", "atrasado", "atrasada", "demora", "defeito", "quebrado",
    "quebrada", "errado", "errada", "faltando", "cancelado", "cancelada", "problema", "decepcionado",
}
STOP_WORDS = {
    "para", "com", "que", "não", "nao", "uma", "por", "mais", "mas", "foi", "meu", "minha", "muito",
    "produto", "pedido", "recebi", "chegou", "ainda", "como", "dos", "das", "esta", "está", "sem",
}


def tokenize_portuguese(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-zÀ-ÿ]{3,}", text or "")]


def score_review_text(text: str) -> tuple[float, float, list[str], list[str]]:
    tokens = tokenize_portuguese(text)
    positive = [token for token in tokens if token in POSITIVE_WORDS]
    negative = [token for token in tokens if token in NEGATIVE_WORDS]
    sentiment_hits = len(positive) + len(negative)
    polarity = (len(positive) - len(negative)) / sentiment_hits if sentiment_hits else 0.0
    subjectivity = sentiment_hits / len(tokens) if tokens else 0.0
    return polarity, min(subjectivity, 1.0), positive, negative


def analyze_review_texts(limit: int = 3000) -> dict:
    sample_size = min(max(int(limit), 1), 10_000)
    sql = ("SELECT review_comment_message FROM order_reviews "
           "WHERE review_comment_message IS NOT NULL AND TRIM(review_comment_message) <> '' "
           f"ORDER BY RAND() LIMIT {sample_size}")
    df = read_df(sql)
    positive_terms: Counter[str] = Counter()
    negative_terms: Counter[str] = Counter()
    topic_terms: Counter[str] = Counter()
    polarities: list[float] = []
    subjectivities: list[float] = []

    for text in df.get("review_comment_message", pd.Series(dtype=str)).fillna("").astype(str):
        polarity, subjectivity, positive, negative = score_review_text(text)
        polarities.append(polarity)
        subjectivities.append(subjectivity)
        positive_terms.update(positive)
        negative_terms.update(negative)
        topic_terms.update(
            token for token in tokenize_portuguese(text)
            if token not in STOP_WORDS and token not in POSITIVE_WORDS and token not in NEGATIVE_WORDS
        )

    count = len(polarities)
    return {
        "sql": sql,
        "comment_count": count,
        "positive_rate": sum(v > 0 for v in polarities) / count if count else 0.0,
        "negative_rate": sum(v < 0 for v in polarities) / count if count else 0.0,
        "neutral_rate": sum(v == 0 for v in polarities) / count if count else 0.0,
        "avg_polarity": sum(polarities) / count if count else 0.0,
        "avg_subjectivity": sum(subjectivities) / count if count else 0.0,
        "positive_keywords": [{"term": t, "count": c} for t, c in positive_terms.most_common(12)],
        "negative_keywords": [{"term": t, "count": c} for t, c in negative_terms.most_common(12)],
        "topic_keywords": [{"term": t, "count": c} for t, c in topic_terms.most_common(40)],
    }
