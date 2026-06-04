"""订单评论文本情感与主题分析。"""
from __future__ import annotations

import re
from collections import Counter

import pandas as pd

from utils.db import run_select

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
    """读取评论正文并输出可序列化的极性、主观性和关键词摘要。"""
    df = run_select(
        f"""
        SELECT review_comment_message
        FROM order_reviews
        WHERE review_comment_message IS NOT NULL
          AND TRIM(review_comment_message) <> ''
        LIMIT {int(limit)}
        """
    )
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
        "comment_count": count,
        "positive_rate": sum(value > 0 for value in polarities) / count if count else 0.0,
        "negative_rate": sum(value < 0 for value in polarities) / count if count else 0.0,
        "neutral_rate": sum(value == 0 for value in polarities) / count if count else 0.0,
        "avg_polarity": sum(polarities) / count if count else 0.0,
        "avg_subjectivity": sum(subjectivities) / count if count else 0.0,
        "positive_keywords": [{"term": term, "count": freq} for term, freq in positive_terms.most_common(10)],
        "negative_keywords": [{"term": term, "count": freq} for term, freq in negative_terms.most_common(10)],
        "topic_keywords": [{"term": term, "count": freq} for term, freq in topic_terms.most_common(12)],
    }


def review_sentiment_proxy_top_categories(limit: int = 10) -> pd.DataFrame:
    """使用 review_score 作为情感代理变量，统计低分占比最高品类。"""
    sql = f"""
    SELECT
        f.product_category_english,
        COUNT(*) AS review_cnt,
        AVG(r.review_score) AS avg_score,
        AVG(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS low_score_rate
    FROM order_reviews r
    JOIN fact_order_items f ON r.order_id = f.order_id
    WHERE f.product_category_english IS NOT NULL
    GROUP BY f.product_category_english
    HAVING review_cnt >= 30
    ORDER BY low_score_rate DESC, review_cnt DESC
    LIMIT {int(limit)}
    """
    return run_select(sql)
