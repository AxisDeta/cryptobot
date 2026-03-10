from __future__ import annotations

import json
from typing import Any

from cryptobot.config import BotSettings
from cryptobot.data.sentiment import engagement_weight
from cryptobot.schemas import EventSignal, SentimentPost


class MySQLStore:
    def __init__(self, settings: BotSettings) -> None:
        if not settings.mysql_enabled:
            raise RuntimeError("MySQL is not configured in .env")
        self.settings = settings

    def _connect(self):
        try:
            import mysql.connector  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("mysql-connector-python is required for MySQL storage") from exc

        return mysql.connector.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            database=self.settings.mysql_database,
            autocommit=False,
        )

    def ensure_schema(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_runs (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exchange VARCHAR(32) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    timeframe VARCHAR(16) NOT NULL,
                    direction_prob_up DOUBLE NOT NULL,
                    expected_volatility DOUBLE NOT NULL,
                    sentiment_index DOUBLE NOT NULL,
                    confidence DOUBLE NOT NULL,
                    recommended_position DOUBLE NOT NULL,
                    num_posts INT NOT NULL,
                    num_events INT NOT NULL,
                    payload_json JSON NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reddit_posts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    run_id BIGINT NOT NULL,
                    ts DATETIME NOT NULL,
                    source VARCHAR(64) NOT NULL,
                    title TEXT NOT NULL,
                    body MEDIUMTEXT NOT NULL,
                    upvotes INT NOT NULL,
                    comments INT NOT NULL,
                    engagement_score DOUBLE NOT NULL,
                    INDEX idx_reddit_run_id (run_id),
                    CONSTRAINT fk_reddit_run FOREIGN KEY (run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS event_signals (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    run_id BIGINT NOT NULL,
                    sentiment VARCHAR(16) NOT NULL,
                    asset VARCHAR(24) NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    horizon VARCHAR(16) NOT NULL,
                    INDEX idx_event_run_id (run_id),
                    CONSTRAINT fk_event_run FOREIGN KEY (run_id) REFERENCES prediction_runs(id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_run(
        self,
        request_meta: dict[str, Any],
        result: dict[str, Any],
        posts: list[SentimentPost],
        events: list[EventSignal],
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO prediction_runs (
                    exchange, symbol, timeframe, direction_prob_up, expected_volatility,
                    sentiment_index, confidence, recommended_position, num_posts, num_events, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(request_meta.get("exchange", "binance")),
                    str(result.get("symbol", "")),
                    str(result.get("timeframe", "")),
                    float(result.get("direction_prob_up", 0.0)),
                    float(result.get("expected_volatility", 0.0)),
                    float(result.get("sentiment_index", 0.0)),
                    float(result.get("confidence", 0.0)),
                    float(result.get("recommended_position", 0.0)),
                    int(result.get("num_posts", 0)),
                    int(result.get("num_events", 0)),
                    json.dumps(result),
                ),
            )
            run_id = int(cur.lastrowid)

            if posts:
                cur.executemany(
                    """
                    INSERT INTO reddit_posts (
                        run_id, ts, source, title, body, upvotes, comments, engagement_score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            run_id,
                            p.ts,
                            p.source,
                            p.title,
                            p.body,
                            p.upvotes,
                            p.comments,
                            float(engagement_weight(p)),
                        )
                        for p in posts
                    ],
                )

            if events:
                cur.executemany(
                    """
                    INSERT INTO event_signals (run_id, sentiment, asset, event_type, horizon)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [(run_id, e.sentiment, e.asset, e.event, e.horizon) for e in events],
                )

            conn.commit()
            return run_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
