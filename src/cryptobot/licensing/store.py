from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cryptobot.config import BotSettings


class LicensingStore:
    def __init__(self, settings: BotSettings) -> None:
        if not settings.mysql_enabled:
            raise RuntimeError("MySQL must be configured for licensing")
        self.settings = settings

    def _connect(self):
        try:
            import mysql.connector  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("mysql-connector-python is required") from exc

        return mysql.connector.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            database=self.settings.mysql_database,
            autocommit=False,
        )

    def _column_exists(self, conn, table: str, column: str) -> bool:
        cur = conn.cursor()
        cur.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (column,))
        return cur.fetchone() is not None

    def _table_exists(self, conn, table: str) -> bool:
        cur = conn.cursor()
        cur.execute("SHOW TABLES LIKE %s", (table,))
        return cur.fetchone() is not None

    def ensure_schema(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NULL,
                    google_sub VARCHAR(255) NULL UNIQUE,
                    is_email_verified TINYINT(1) NOT NULL DEFAULT 0,
                    is_admin TINYINT(1) NOT NULL DEFAULT 0,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            if not self._column_exists(conn, "app_users", "is_admin"):
                cur.execute("ALTER TABLE app_users ADD COLUMN is_admin TINYINT(1) NOT NULL DEFAULT 0")
            if not self._column_exists(conn, "app_users", "is_active"):
                cur.execute("ALTER TABLE app_users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1")


            if not self._column_exists(conn, "activation_licenses", "activation_key_value"):
                cur.execute("ALTER TABLE activation_licenses ADD COLUMN activation_key_value VARCHAR(128) NULL")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    timeframe VARCHAR(16) NOT NULL,
                    action VARCHAR(32) NOT NULL,
                    confidence DOUBLE NOT NULL DEFAULT 0,
                    outcome VARCHAR(16) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_so_user (user_id),
                    INDEX idx_so_outcome (outcome),
                    CONSTRAINT fk_so_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    used_at DATETIME NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_evt_user (user_id),
                    CONSTRAINT fk_evt_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    used_at DATETIME NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_prt_user (user_id),
                    CONSTRAINT fk_prt_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_payments (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    provider VARCHAR(32) NOT NULL,
                    reference VARCHAR(128) NOT NULL UNIQUE,
                    plan_code VARCHAR(32) NOT NULL,
                    currency VARCHAR(8) NOT NULL,
                    amount_cents BIGINT NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    provider_payload JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_bp_user (user_id),
                    CONSTRAINT fk_bp_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS activation_licenses (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    payment_id BIGINT NOT NULL UNIQUE,
                    plan_code VARCHAR(32) NOT NULL,
                    duration_days INT NOT NULL,
                    activation_key_hash VARCHAR(64) NOT NULL UNIQUE,
                    activation_key_hint VARCHAR(32) NOT NULL,
                    activation_key_value VARCHAR(128) NULL,
                    status VARCHAR(32) NOT NULL,
                    issued_at DATETIME NOT NULL,
                    activation_deadline_at DATETIME NOT NULL,
                    activated_at DATETIME NULL,
                    expires_at DATETIME NULL,
                    bound_device_id VARCHAR(255) NULL,
                    max_devices INT NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_al_user (user_id),
                    CONSTRAINT fk_al_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
                    CONSTRAINT fk_al_payment FOREIGN KEY (payment_id) REFERENCES billing_payments(id) ON DELETE CASCADE
                )
                """
            )

            if not self._column_exists(conn, "activation_licenses", "activation_key_value"):
                cur.execute("ALTER TABLE activation_licenses ADD COLUMN activation_key_value VARCHAR(128) NULL")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    timeframe VARCHAR(16) NOT NULL,
                    action VARCHAR(32) NOT NULL,
                    confidence DOUBLE NOT NULL DEFAULT 0,
                    outcome VARCHAR(16) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_so_user (user_id),
                    INDEX idx_so_outcome (outcome),
                    CONSTRAINT fk_so_user FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _dt(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM app_users WHERE LOWER(email)=LOWER(%s)", (email,))
            return cur.fetchone()
        finally:
            conn.close()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM app_users WHERE id=%s", (user_id,))
            return cur.fetchone()
        finally:
            conn.close()

    def create_user(
        self,
        email: str,
        password_hash: str | None,
        google_sub: str | None = None,
        verified: bool = False,
        is_admin: bool = False,
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO app_users (email, password_hash, google_sub, is_email_verified, is_admin, is_active) VALUES (%s, %s, %s, %s, %s, 1)",
                (email, password_hash, google_sub, 1 if verified else 0, 1 if is_admin else 0),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def upsert_google_user(self, email: str, google_sub: str, is_admin: bool = False) -> int:
        existing = self.get_user_by_email(email)
        if existing:
            conn = self._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE app_users SET google_sub=%s, is_email_verified=1, is_admin=GREATEST(is_admin,%s) WHERE id=%s",
                    (google_sub, 1 if is_admin else 0, int(existing["id"])),
                )
                conn.commit()
                return int(existing["id"])
            finally:
                conn.close()
        return self.create_user(email=email, password_hash=None, google_sub=google_sub, verified=True, is_admin=is_admin)

    def create_email_verification(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO email_verification_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, token_hash, self._dt(expires_at)),
            )
            conn.commit()
        finally:
            conn.close()

    def verify_email_token(self, token_hash: str, now: datetime) -> int | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM email_verification_tokens WHERE token_hash=%s FOR UPDATE", (token_hash,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            if row.get("used_at") is not None or row["expires_at"] < self._dt(now):
                conn.rollback()
                return None

            user_id = int(row["user_id"])
            cur2 = conn.cursor()
            cur2.execute("UPDATE email_verification_tokens SET used_at=%s WHERE id=%s", (self._dt(now), int(row["id"])))
            cur2.execute("UPDATE app_users SET is_email_verified=1 WHERE id=%s", (user_id,))
            conn.commit()
            return user_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_password_reset(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE password_reset_tokens SET used_at=%s WHERE user_id=%s AND used_at IS NULL", (self._dt(datetime.utcnow()), int(user_id)))
            cur.execute(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (int(user_id), token_hash, self._dt(expires_at)),
            )
            conn.commit()
        finally:
            conn.close()

    def consume_password_reset_token(self, token_hash: str, now: datetime) -> int | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM password_reset_tokens WHERE token_hash=%s FOR UPDATE", (token_hash,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            if row.get("used_at") is not None or row["expires_at"] < self._dt(now):
                conn.rollback()
                return None
            user_id = int(row["user_id"])
            cur2 = conn.cursor()
            cur2.execute("UPDATE password_reset_tokens SET used_at=%s WHERE id=%s", (self._dt(now), int(row["id"])))
            conn.commit()
            return user_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_user_password(self, user_id: int, password_hash: str) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE app_users SET password_hash=%s WHERE id=%s",
                (password_hash, int(user_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def create_payment(self, user_id: int, provider: str, reference: str, plan_code: str, currency: str, amount_cents: int, status: str) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO billing_payments (user_id, provider, reference, plan_code, currency, amount_cents, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, provider, reference, plan_code, currency, int(amount_cents), status),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def get_payment_by_reference(self, reference: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM billing_payments WHERE reference=%s", (reference,))
            return cur.fetchone()
        finally:
            conn.close()

    def update_payment(self, payment_id: int, status: str, payload: dict[str, Any] | None = None) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE billing_payments SET status=%s, provider_payload=%s WHERE id=%s",
                (status, json.dumps(payload) if payload is not None else None, payment_id),
            )
            conn.commit()
        finally:
            conn.close()

    def create_license(
        self,
        user_id: int,
        payment_id: int,
        plan_code: str,
        duration_days: int,
        activation_key_hash: str,
        activation_key_hint: str,
        activation_key_value: str | None,
        status: str,
        issued_at: datetime,
        activation_deadline_at: datetime,
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO activation_licenses (
                  user_id, payment_id, plan_code, duration_days, activation_key_hash, activation_key_hint, activation_key_value,
                  status, issued_at, activation_deadline_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    payment_id,
                    plan_code,
                    duration_days,
                    activation_key_hash,
                    activation_key_hint,
                    activation_key_value,
                    status,
                    self._dt(issued_at),
                    self._dt(activation_deadline_at),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()
    def get_license_by_key_hash(self, key_hash: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM activation_licenses WHERE activation_key_hash=%s", (key_hash,))
            return cur.fetchone()
        finally:
            conn.close()

    def activate_license(self, license_id: int, device_id: str, activated_at: datetime, expires_at: datetime) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE activation_licenses
                SET status='active', bound_device_id=%s, activated_at=%s, expires_at=%s
                WHERE id=%s
                """,
                (device_id, self._dt(activated_at), self._dt(expires_at), license_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_active_license_for_user(self, user_id: int, now: datetime) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT * FROM activation_licenses
                WHERE user_id=%s AND status='active' AND expires_at IS NOT NULL AND expires_at > %s
                ORDER BY expires_at DESC LIMIT 1
                """,
                (user_id, self._dt(now)),
            )
            return cur.fetchone()
        finally:
            conn.close()


    def get_latest_active_expiry_for_user(self, user_id: int, now: datetime) -> datetime | None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(expires_at)
                FROM activation_licenses
                WHERE user_id=%s AND status='active' AND expires_at IS NOT NULL AND expires_at > %s
                """,
                (int(user_id), self._dt(now)),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None
        finally:
            conn.close()

    def supersede_other_active_licenses(self, user_id: int, keep_license_id: int) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE activation_licenses
                SET status='superseded'
                WHERE user_id=%s AND status='active' AND id<>%s
                """,
                (int(user_id), int(keep_license_id)),
            )
            conn.commit()
        finally:
            conn.close()

    def list_user_licenses(self, user_id: int, limit: int = 30) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, plan_code, status, issued_at, activated_at, expires_at, activation_key_hint, activation_key_value AS activation_key, bound_device_id
                FROM activation_licenses
                WHERE user_id=%s
                ORDER BY id DESC
                LIMIT %s
                """,
                (int(user_id), int(limit)),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def expire_active_licenses(self, now: datetime) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE activation_licenses
                SET status='expired'
                WHERE status='active' AND expires_at IS NOT NULL AND expires_at <= %s
                """,
                (self._dt(now),),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()

    def create_signal_outcome(self, user_id: int, symbol: str, timeframe: str, action: str, confidence: float, outcome: str = "pending") -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO signal_outcomes (user_id, symbol, timeframe, action, confidence, outcome)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (int(user_id), str(symbol), str(timeframe), str(action), float(confidence), str(outcome)),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def update_signal_outcome(self, signal_id: int, user_id: int, outcome: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE signal_outcomes SET outcome=%s WHERE id=%s AND user_id=%s",
                (str(outcome), int(signal_id), int(user_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0
        finally:
            conn.close()

    def signal_outcomes_analytics(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            if not self._table_exists(conn, "signal_outcomes"):
                return {"counts": {"win": 0, "loss": 0, "skip": 0, "pending": 0}, "total": 0, "users_with_signals": 0, "avg_per_user": {"win": 0.0, "loss": 0.0, "skip": 0.0, "pending": 0.0}}
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END),0) AS wins,
                  COALESCE(SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END),0) AS losses,
                  COALESCE(SUM(CASE WHEN outcome='skip' THEN 1 ELSE 0 END),0) AS skips,
                  COALESCE(SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END),0) AS pendings,
                  COUNT(*) AS total,
                  COUNT(DISTINCT user_id) AS users_with_signals
                FROM signal_outcomes
                """
            )
            row = cur.fetchone() or {}
            wins = int(row.get("wins") or 0)
            losses = int(row.get("losses") or 0)
            skips = int(row.get("skips") or 0)
            pendings = int(row.get("pendings") or 0)
            total = int(row.get("total") or 0)
            users = int(row.get("users_with_signals") or 0)
            denom = users if users > 0 else 1
            return {
                "counts": {"win": wins, "loss": losses, "skip": skips, "pending": pendings},
                "total": total,
                "users_with_signals": users,
                "avg_per_user": {
                    "win": round(wins / denom, 4) if users else 0.0,
                    "loss": round(losses / denom, 4) if users else 0.0,
                    "skip": round(skips / denom, 4) if users else 0.0,
                    "pending": round(pendings / denom, 4) if users else 0.0,
                },
            }
        finally:
            conn.close()


    # Admin methods
    def list_users(self, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT
                    u.id,
                    u.email,
                    u.is_email_verified,
                    u.is_admin,
                    u.is_active,
                    u.created_at,
                    SUBSTRING_INDEX(u.email, '@', 1) AS display_name,
                    (
                        SELECT COUNT(*)
                        FROM activation_licenses l2
                        WHERE l2.user_id=u.id AND l2.status='active'
                    ) AS active_license_count,
                    (
                        SELECT COUNT(*)
                        FROM billing_payments p2
                        WHERE p2.user_id=u.id AND p2.status='completed'
                    ) AS completed_payments_count,
                    (
                        SELECT l3.plan_code
                        FROM activation_licenses l3
                        WHERE l3.user_id=u.id
                        ORDER BY l3.id DESC
                        LIMIT 1
                    ) AS latest_plan_code,
                    (
                        SELECT l4.status
                        FROM activation_licenses l4
                        WHERE l4.user_id=u.id
                        ORDER BY l4.id DESC
                        LIMIT 1
                    ) AS latest_license_status,
                    (
                        SELECT l5.issued_at
                        FROM activation_licenses l5
                        WHERE l5.user_id=u.id
                        ORDER BY l5.id DESC
                        LIMIT 1
                    ) AS latest_issued_at,
                    (
                        SELECT l6.activated_at
                        FROM activation_licenses l6
                        WHERE l6.user_id=u.id
                        ORDER BY l6.id DESC
                        LIMIT 1
                    ) AS latest_activated_at,
                    (
                        SELECT l7.expires_at
                        FROM activation_licenses l7
                        WHERE l7.user_id=u.id
                        ORDER BY l7.id DESC
                        LIMIT 1
                    ) AS latest_expires_at
                FROM app_users u
                ORDER BY u.id DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def set_user_admin(self, user_id: int, is_admin: bool) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE app_users SET is_admin=%s WHERE id=%s", (1 if is_admin else 0, int(user_id)))
            conn.commit()
        finally:
            conn.close()

    def set_user_active(self, user_id: int, is_active: bool) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE app_users SET is_active=%s WHERE id=%s", (1 if is_active else 0, int(user_id)))
            conn.commit()
        finally:
            conn.close()

    def list_payments(self, limit: int = 300) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT p.id, p.user_id, u.email, p.provider, p.reference, p.plan_code, p.currency, p.amount_cents, p.status, p.created_at, p.updated_at
                FROM billing_payments p
                JOIN app_users u ON u.id=p.user_id
                ORDER BY p.id DESC LIMIT %s
                """,
                (int(limit),),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def list_licenses(self, limit: int = 300) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT l.id, l.user_id, u.email, l.payment_id, l.plan_code, l.duration_days, l.activation_key_hint, l.status,
                       l.issued_at, l.activation_deadline_at, l.activated_at, l.expires_at, l.bound_device_id
                FROM activation_licenses l
                JOIN app_users u ON u.id=l.user_id
                ORDER BY l.id DESC LIMIT %s
                """,
                (int(limit),),
            )
            return list(cur.fetchall())
        finally:
            conn.close()

    def revoke_license(self, license_id: int) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE activation_licenses SET status='revoked' WHERE id=%s", (int(license_id),))
            conn.commit()
        finally:
            conn.close()

    def clear_license_device(self, license_id: int) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE activation_licenses SET bound_device_id=NULL WHERE id=%s", (int(license_id),))
            conn.commit()
        finally:
            conn.close()

    def list_prediction_runs(self, limit: int = 300) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if not self._table_exists(conn, "prediction_runs"):
                return []
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM prediction_runs ORDER BY id DESC LIMIT %s", (int(limit),))
            return list(cur.fetchall())
        finally:
            conn.close()

    def overview(self) -> dict[str, int]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM app_users")
            users = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM app_users WHERE is_active=1")
            active_users = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM activation_licenses WHERE status='active'")
            active_licenses = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM billing_payments WHERE status='completed'")
            completed_payments = int(cur.fetchone()[0])
            predictions = 0
            if self._table_exists(conn, "prediction_runs"):
                cur.execute("SELECT COUNT(*) FROM prediction_runs")
                predictions = int(cur.fetchone()[0])
            return {
                "users": users,
                "active_users": active_users,
                "active_licenses": active_licenses,
                "completed_payments": completed_payments,
                "prediction_runs": predictions,
            }
        finally:
            conn.close()









