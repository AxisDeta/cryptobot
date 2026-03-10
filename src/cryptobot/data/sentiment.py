from __future__ import annotations

import math
from datetime import datetime

from cryptobot.schemas import SentimentPost


class RedditSentimentClient:
    """PRAW wrapper for pulling subreddit posts with engagement metadata."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.username = username
        self.password = password

    def fetch_new_posts(self, subreddit: str, limit: int = 100) -> list[SentimentPost]:
        try:
            import praw  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("praw is required for Reddit ingestion") from exc

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            username=self.username,
            password=self.password,
        )
        posts: list[SentimentPost] = []
        for p in reddit.subreddit(subreddit).new(limit=limit):
            posts.append(
                SentimentPost(
                    ts=datetime.utcfromtimestamp(float(p.created_utc)),
                    source=f"reddit:{subreddit}",
                    title=p.title or "",
                    body=p.selftext or "",
                    upvotes=int(p.score or 0),
                    comments=int(p.num_comments or 0),
                )
            )
        return posts


def engagement_weight(post: SentimentPost) -> float:
    return math.log(post.upvotes + post.comments + 1.0)
