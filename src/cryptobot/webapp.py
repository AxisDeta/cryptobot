from __future__ import annotations

import json
import logging
from functools import lru_cache
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from cryptobot.config import BotSettings
from cryptobot.licensing.oauth import exchange_google_code, fetch_google_profile, google_auth_url, new_oauth_state
from cryptobot.licensing.payments import PaystackClient, PesapalClient
from cryptobot.licensing.security import PLANS
from cryptobot.licensing.service import LicensingService
from cryptobot.service import AdhocBacktestRequest, LivePredictionRequest, generate_live_prediction, model_cache_overview, run_ad_hoc_backtest

logger = logging.getLogger(__name__)


class PredictPayload(BaseModel):
    market_type: str = Field(default="crypto", pattern="^(crypto|forex)$")
    exchange: str = Field(default="binance")
    symbol: str | None = None
    timeframe: str | None = None


class SignupPayload(BaseModel):
    email: str
    password: str


class LoginPayload(BaseModel):
    email: str
    password: str


class ForgotPasswordPayload(BaseModel):
    email: str


class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str


class CheckoutPayload(BaseModel):
    provider: str = Field(pattern="^(paystack|pesapal)$")
    plan_code: str = Field(pattern="^(test_ksh1|monthly|quarterly|yearly)$")


class ActivatePayload(BaseModel):
    activation_key: str
    device_id: str


class SignalOutcomeCreatePayload(BaseModel):
    symbol: str
    timeframe: str
    action: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    outcome: str = Field(default="pending", pattern="^(pending|win|loss|skip)$")


class SignalOutcomeUpdatePayload(BaseModel):
    outcome: str = Field(pattern="^(pending|win|loss|skip)$")


class AdminUserPatchPayload(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


class AdminLicenseActionPayload(BaseModel):
    action: str = Field(pattern="^(revoke|clear_device)$")


class AdminBacktestPayload(BaseModel):
    market_type: str = Field(default="crypto", pattern="^(crypto|forex)$")
    exchange: str = "binance"
    symbol: str
    timeframe: str
    horizon_bars: int = Field(default=96, ge=20, le=500)
    threshold: float = Field(default=0.55, ge=0.5, le=0.8)


@lru_cache(maxsize=1)
def _svc() -> LicensingService:
    return LicensingService(BotSettings.from_env())


def _require_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    return int(user_id)


def _require_admin(request: Request) -> int:
    user_id = _require_user_id(request)
    if not _svc().is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id



def _same_host_callback(request: Request, configured_url: str | None, path: str) -> str:
    request_base = str(request.base_url).rstrip("/")
    fallback = f"{request_base}{path}"
    cfg = (configured_url or "").strip()
    if not cfg:
        return fallback
    try:
        req_host = (request.url.hostname or "").lower()
        cfg_host = (urlparse(cfg).hostname or "").lower()
        if req_host in {"localhost", "127.0.0.1"} and cfg_host in {"localhost", "127.0.0.1"} and req_host != cfg_host:
            return fallback
    except Exception:
        return fallback
    return cfg
def create_app() -> FastAPI:
    app = FastAPI(title="CryptoBot Live", version="0.1.0")
    settings = BotSettings.from_env()
    app.add_middleware(SessionMiddleware, secret_key=settings.app_session_secret or "change-me")

    templates = Jinja2Templates(directory="src/cryptobot/web/templates")
    app.mount("/static", StaticFiles(directory="src/cryptobot/web/static"), name="static")

    def payment_result_page(message: str, title: str = "Payment Status", auto_redirect: bool = True, status_code: int = 200) -> HTMLResponse:
        refresh = '<meta http-equiv="refresh" content="5;url=/app" />' if auto_redirect else ""
        footer = '<small>Redirecting automatically in 5 seconds...</small>' if auto_redirect else ""
        return HTMLResponse(
            f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    {refresh}
    <title>{title}</title>
    <style>
      body {{ margin:0; font-family:Segoe UI,Trebuchet MS,sans-serif; background:#0a1320; color:#ecf2fa; min-height:100vh; display:grid; place-items:center; }}
      .card {{ width:min(640px,92vw); background:#121f32; border:1px solid rgba(255,255,255,0.12); border-radius:14px; padding:22px; box-shadow:0 14px 28px rgba(0,0,0,0.3); }}
      h1 {{ margin:0 0 10px; font-size:1.4rem; }}
      p {{ margin:0 0 14px; color:#c6d4e7; line-height:1.5; }}
      a {{ display:inline-block; background:#f59e0b; color:#111827; text-decoration:none; border-radius:10px; padding:10px 14px; font-weight:700; }}
      small {{ display:block; margin-top:10px; color:#98acc5; }}
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h1>{title}</h1>
      <p>{message}</p>
      <a href=\"/app\">Return to Homepage</a>
      {footer}
    </div>
  </body>
</html>
            """,
            status_code=status_code,
        )

    def payment_success_page() -> HTMLResponse:
        return payment_result_page(
            "Payment confirmed. Activation key sent to your email. Return to app and activate key.",
            title="Payment confirmed",
            auto_redirect=True,
            status_code=200,
        )

    pesapal_cached_ipn_id: str | None = None

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/app")
        return RedirectResponse("/login")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/app")
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/about", response_class=HTMLResponse)
    async def about_page(request: Request):
        return templates.TemplateResponse("about.html", {"request": request})

    @app.get("/tutorial", response_class=HTMLResponse)
    async def tutorial_page(request: Request):
        return templates.TemplateResponse("tutorial.html", {"request": request})

    @app.get("/support", response_class=HTMLResponse)
    async def support_page(request: Request):
        return templates.TemplateResponse("support.html", {"request": request})

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_page(request: Request):
        return templates.TemplateResponse("privacy.html", {"request": request})
    @app.get("/app", response_class=HTMLResponse)
    async def app_page(request: Request):
        user_id = request.session.get("user_id")
        if not user_id:
            return RedirectResponse("/login")
        user = _svc().store.get_user_by_id(int(user_id))
        if not user or not bool(user.get("is_active", 1)):
            request.session.clear()
            return RedirectResponse("/login")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "user_email": str(user["email"]),
                "user_is_admin": bool(user.get("is_admin")),
            },
        )

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request):
        user_id = request.session.get("user_id")
        if not user_id:
            return RedirectResponse("/login")
        if not _svc().is_admin_user(int(user_id)):
            return RedirectResponse("/app")
        return templates.TemplateResponse("admin.html", {"request": request})

    @app.get("/logout")
    async def logout_redirect(request: Request):
        request.session.clear()
        return RedirectResponse("/login")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/signup")
    async def auth_signup(payload: SignupPayload):
        try:
            result = _svc().signup_email(payload.email, payload.password)
            return JSONResponse({"success": True, **result})
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid request") from exc

    @app.get("/auth/verify-email")
    async def auth_verify_email(token: str):
        uid = _svc().verify_email(token)
        if not uid:
            return HTMLResponse("Email verification failed or expired.", status_code=400)
        return HTMLResponse("Email verified successfully. You can now login.")

    @app.post("/api/auth/login")
    async def auth_login(request: Request, payload: LoginPayload):
        svc = _svc()
        user = svc.login_email(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_id = int(user["id"])
        request.session["user_id"] = user_id
        request.session["email"] = str(user["email"])
        return JSONResponse(
            {
                "success": True,
                "user_is_admin": bool(user.get("is_admin")),
                "activation_key": svc.get_preferred_activation_key(user_id),
            }
        )

    @app.post("/api/auth/forgot-password")
    async def auth_forgot_password(request: Request):
        email = ""
        new_password = ""
        confirm_password = ""

        try:
            payload = await request.json()
            if isinstance(payload, dict):
                email = str(payload.get("email") or "").strip()
                new_password = str(payload.get("new_password") or "")
                confirm_password = str(payload.get("confirm_password") or "")
        except Exception:
            pass

        if not email:
            email = str(request.query_params.get("email") or "").strip()
        if not new_password:
            new_password = str(request.query_params.get("new_password") or "")
        if not confirm_password:
            confirm_password = str(request.query_params.get("confirm_password") or "")

        if not email or not new_password or not confirm_password:
            try:
                form = await request.form()
                email = email or str(form.get("email") or "").strip()
                new_password = new_password or str(form.get("new_password") or "")
                confirm_password = confirm_password or str(form.get("confirm_password") or "")
            except Exception:
                pass

        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        try:
            ok = _svc().reset_password_by_email(email=email, new_password=new_password)
            if not ok:
                raise HTTPException(status_code=404, detail="Account not found")
            logger.info("Forgot-password direct reset successful for email=%s", email)
            return JSONResponse({"success": True, "message": "Password reset successful. You can now login."})
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Password reset failed") from exc
    @app.post("/api/auth/reset-password")
    async def auth_reset_password(request: Request):
        token = ""
        new_password = ""
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                token = str(payload.get("token") or "").strip()
                new_password = str(payload.get("new_password") or "")
        except Exception:
            token = ""
            new_password = ""

        if not token:
            token = str(request.query_params.get("token") or "").strip()
        if not new_password:
            new_password = str(request.query_params.get("new_password") or "")
        if not token or not new_password:
            try:
                form = await request.form()
                token = token or str(form.get("token") or "").strip()
                new_password = new_password or str(form.get("new_password") or "")
            except Exception:
                pass

        try:
            ok = _svc().reset_password(token, new_password)
            if not ok:
                raise HTTPException(status_code=400, detail="Reset link is invalid or expired")
            return JSONResponse({"success": True, "message": "Password reset successful. You can now login."})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid request") from exc
    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        request.session.clear()
        return JSONResponse({"success": True})

    @app.get("/auth/google/login")
    async def google_login(request: Request):
        s = BotSettings.from_env()
        if not s.google_client_id or not s.google_client_secret:
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")

        # Keep callback host aligned with current app host to preserve session cookie for state checks.
        request_base = str(request.base_url).rstrip("/")
        configured_redirect = (s.google_redirect_uri or "").strip()
        callback_uri = configured_redirect or f"{request_base}/auth/google/callback"

        try:

            req_host = (request.url.hostname or "").lower()
            cfg_host = (urlparse(callback_uri).hostname or "").lower()
            if req_host in {"localhost", "127.0.0.1"} and cfg_host in {"localhost", "127.0.0.1"} and req_host != cfg_host:
                callback_uri = f"{request_base}/auth/google/callback"
        except Exception:
            pass

        state = new_oauth_state()
        request.session["google_oauth_state"] = state
        request.session["google_oauth_redirect_uri"] = callback_uri
        return RedirectResponse(google_auth_url(s, state, callback_uri))

    @app.get("/auth/google/callback")
    async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
        if error:
            return HTMLResponse(f"Google authentication failed: {error}", status_code=400)

        expected = request.session.pop("google_oauth_state", None)
        callback_uri = request.session.pop("google_oauth_redirect_uri", None)
        if not expected or state != expected:
            return HTMLResponse("Google state validation failed. Use one host consistently (localhost or 127.0.0.1).", status_code=400)
        if not code:
            return HTMLResponse("Missing Google auth code.", status_code=400)

        s = BotSettings.from_env()
        token = exchange_google_code(s, code, callback_uri)
        access = token.get("access_token")
        if not access:
            return HTMLResponse("Google token exchange failed.", status_code=400)
        profile = fetch_google_profile(str(access))
        email = (profile.get("email") or "").strip().lower()
        sub = (profile.get("sub") or "").strip()
        if not email or not sub:
            return HTMLResponse("Google profile missing email/sub.", status_code=400)
        user_id = _svc().login_google(email=email, sub=sub)
        request.session["user_id"] = user_id
        request.session["email"] = email
        return RedirectResponse("/app")

    @app.get("/api/billing/plans")
    async def billing_plans(request: Request):
        _require_user_id(request)
        return JSONResponse({"plans": [vars(p) for p in PLANS.values()]})

    @app.post("/api/billing/checkout")
    async def billing_checkout(request: Request, payload: CheckoutPayload):
        user_id = _require_user_id(request)
        settings_local = BotSettings.from_env()
        svc = _svc()
        user = svc.store.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session user")
        if not bool(user.get("is_email_verified")):
            raise HTTPException(status_code=403, detail="Verify your email before payment")

        plan = PLANS[payload.plan_code]
        # Pesapal account limit safeguard: force Paystack for plans above KSh 2,000.
        provider = payload.provider
        if int(plan.amount_cents_usd) > 200000:
            provider = "paystack"

        if provider == "paystack":
            if not settings_local.paystack_secret_key:
                raise HTTPException(status_code=503, detail="Payments are not configured yet.")

            reference = svc.create_checkout_record(user_id, "paystack", plan.code, plan.amount_cents_usd, settings_local.paystack_currency)
            payment_row = svc.store.get_payment_by_reference(reference)
            payment_id = int(payment_row["id"]) if payment_row else 0
            callback = _same_host_callback(request, settings_local.paystack_callback_url or f"{settings_local.app_base_url.rstrip('/')}/billing/paystack/callback", "/billing/paystack/callback")

            client = PaystackClient(settings_local)
            metadata = {
                "user_id": user_id,
                "email": str(user["email"]),
                "plan_code": plan.code,
                "display_currency": "USD",
                "display_price_usd": round(plan.amount_cents_usd / 100.0, 2),
                "checkout_currency": settings_local.paystack_currency,
                "checkout_price": round(plan.amount_cents_usd / 100.0, 2),
            }

            try:
                status_code, body = client.initialize(
                    email=str(user["email"]),
                    amount_cents=plan.amount_cents_usd,
                    reference=reference,
                    callback_url=callback,
                    currency=settings_local.paystack_currency,
                    metadata=metadata,
                )
            except Exception as exc:
                if payment_id:
                    svc.store.update_payment(payment_id, "init_failed", {"error": str(exc)})
                raise HTTPException(status_code=502, detail="Unable to start checkout. Try again.") from exc

            if status_code >= 300 or not body.get("status"):
                if payment_id:
                    svc.store.update_payment(payment_id, "init_failed", body)
                raise HTTPException(status_code=502, detail=client.friendly_error(body))

            if payment_id:
                svc.store.update_payment(payment_id, "initialized", body)

            auth_url = body.get("data", {}).get("authorization_url")
            return JSONResponse(
                {
                    "success": True,
                    "reference": reference,
                    "authorization_url": auth_url,
                    "redirect_url": auth_url,
                    "access_code": body.get("data", {}).get("access_code"),
                }
            )

        if not settings_local.pesapal_consumer_key or not settings_local.pesapal_consumer_secret:
            raise HTTPException(status_code=503, detail="Pesapal is not configured")

        reference = svc.create_checkout_record(user_id, "pesapal", plan.code, plan.amount_cents_usd, settings_local.pesapal_currency)
        payment_row = svc.store.get_payment_by_reference(reference)
        payment_id = int(payment_row["id"]) if payment_row else 0

        client = PesapalClient(settings_local)
        token, token_err = client.get_token()
        if token_err or not token:
            if payment_id:
                svc.store.update_payment(payment_id, "init_failed", token_err or {"message": "token_error"})
            raise HTTPException(status_code=502, detail="Failed to initialize checkout. Please try again.")

        ipn_url = _same_host_callback(request, settings_local.pesapal_ipn_url or f"{settings_local.app_base_url.rstrip('/')}/api/payments/pesapal/ipn", "/api/payments/pesapal/ipn")
        nonlocal pesapal_cached_ipn_id
        ipn_id = pesapal_cached_ipn_id
        ipn_err = None
        if not ipn_id:
            ipn_id, ipn_err = client.register_ipn(token, ipn_url)
            if not ipn_err and ipn_id:
                pesapal_cached_ipn_id = str(ipn_id)
        if ipn_err or not ipn_id:
            if payment_id:
                svc.store.update_payment(payment_id, "init_failed", ipn_err or {"message": "ipn_registration_error"})
            raise HTTPException(status_code=502, detail="Failed to initialize checkout. Please try again.")

        callback = _same_host_callback(request, settings_local.pesapal_callback_url or f"{settings_local.app_base_url.rstrip('/')}/billing/pesapal/callback", "/billing/pesapal/callback")
        status_code, body = client.submit_order(
            token=token,
            ipn_id=ipn_id,
            reference=reference,
            email=str(user["email"]),
            amount=round(plan.amount_cents_usd / 100.0, 2),
            callback_url=callback,
            currency=settings_local.pesapal_currency,
        )

        redirect_url = None
        if isinstance(body, dict):
            redirect_url = body.get("redirect_url") or body.get("payment_url") or (body.get("data") or {}).get("redirect_url")
        if status_code >= 300 or not redirect_url:
            if payment_id:
                svc.store.update_payment(payment_id, "init_failed", body if isinstance(body, dict) else {"message": str(body)})
            raise HTTPException(status_code=502, detail="Failed to initialize checkout. Please try again.")

        if payment_id:
            svc.store.update_payment(payment_id, "initialized", body)

        return JSONResponse({"success": True, "reference": reference, "redirect_url": redirect_url, "authorization_url": redirect_url})

    @app.get("/api/billing/verify-callback")
    async def billing_verify_callback(request: Request, reference: str | None = None, trxref: str | None = None):
        user_id = _require_user_id(request)
        ref = (reference or trxref or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="Missing payment reference.")

        tx = _svc().store.get_payment_by_reference(ref)
        if not tx:
            raise HTTPException(status_code=404, detail="Payment reference not found.")
        if int(tx["user_id"]) != int(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")

        if str(tx.get("status") or "").lower() == "completed":
            return JSONResponse({"success": True, "message": "Payment already applied.", "status": tx.get("status")})

        s = BotSettings.from_env()
        status_code, body = PaystackClient(s).verify(ref)
        if status_code >= 300 or not body.get("status"):
            _svc().store.update_payment(int(tx["id"]), "verify_failed", body)
            raise HTTPException(status_code=502, detail="Could not verify payment.")

        data = body.get("data") or {}
        paid_ok = data.get("status") == "success"
        amount_ok = int(data.get("amount") or 0) == int(tx["amount_cents"])
        currency_ok = (str(data.get("currency") or "").upper() == str(tx["currency"] or "").upper())

        if not paid_ok or not amount_ok or not currency_ok:
            _svc().store.update_payment(int(tx["id"]), "verify_mismatch", body)
            raise HTTPException(status_code=400, detail="Payment verification mismatch.")

        _svc().fulfill_payment(ref, provider_payload=body)
        return JSONResponse({"success": True, "message": "Purchase completed successfully."})

    @app.get("/billing/paystack/callback")
    async def paystack_callback(reference: str | None = None, trxref: str | None = None):
        ref = (reference or trxref or "").strip()
        if not ref:
            return HTMLResponse("Missing payment reference", status_code=400)

        s = BotSettings.from_env()
        if not s.paystack_secret_key:
            return HTMLResponse("Paystack not configured", status_code=503)

        svc = _svc()
        tx = svc.store.get_payment_by_reference(ref)
        if not tx:
            return HTMLResponse("Payment reference not found.", status_code=404)

        status_code, body = PaystackClient(s).verify(ref)
        if status_code >= 300 or not body.get("status"):
            svc.store.update_payment(int(tx["id"]), "verify_failed", body)
            return HTMLResponse("Could not verify payment.", status_code=502)

        data = body.get("data") or {}
        paid_ok = data.get("status") == "success"
        amount_ok = int(data.get("amount") or 0) == int(tx["amount_cents"])
        currency_ok = (str(data.get("currency") or "").upper() == str(tx["currency"] or "").upper())

        if not paid_ok or not amount_ok or not currency_ok:
            svc.store.update_payment(int(tx["id"]), "verify_mismatch", body)
            return HTMLResponse("Payment verification mismatch.", status_code=400)

        svc.fulfill_payment(ref, provider_payload=body)
        return payment_success_page()

    @app.post("/api/payments/paystack/webhook")
    async def paystack_webhook(request: Request):
        s = BotSettings.from_env()
        raw = await request.body()
        sig = request.headers.get("x-paystack-signature")
        if not PaystackClient(s).is_valid_signature(raw, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")
        payload = await request.json()
        if payload.get("event") == "charge.success":
            ref = str((payload.get("data") or {}).get("reference") or "")
            if ref:
                try:
                    _svc().fulfill_payment(ref, provider_payload=payload)
                except Exception:
                    pass
        return JSONResponse({"success": True})

    @app.get("/billing/pesapal/callback")
    async def pesapal_callback(
        OrderTrackingId: str | None = None,
        OrderMerchantReference: str | None = None,
        orderTrackingId: str | None = None,
        orderMerchantReference: str | None = None,
    ):
        ref = (OrderMerchantReference or orderMerchantReference or "").strip()
        tracking = (OrderTrackingId or orderTrackingId or "").strip()
        if not ref or not tracking:
            return payment_result_page(
                "Missing Pesapal callback parameters. Return to app and try payment confirmation again.",
                title="Payment callback incomplete",
                auto_redirect=True,
                status_code=400,
            )

        tx = _svc().store.get_payment_by_reference(ref)
        if not tx:
            return payment_result_page(
                "Payment reference not found. Return to app and retry checkout.",
                title="Payment not found",
                auto_redirect=True,
                status_code=404,
            )

        s = BotSettings.from_env()
        client = PesapalClient(s)
        token, token_err = client.get_token()
        if token_err or not token:
            _svc().store.update_payment(int(tx["id"]), "verify_failed", token_err or {"message": "token_error"})
            return payment_result_page("Failed to get authentication token.", title="Payment verification pending", auto_redirect=False, status_code=502)

        status_code, status = client.get_transaction_status(token, tracking)
        desc = str((status or {}).get("payment_status_description", "")).lower()
        if status_code >= 300 or "completed" not in desc:
            _svc().store.update_payment(int(tx["id"]), "verify_failed", status)
            return payment_result_page("Payment not completed yet. Please return to app and retry verification shortly.", title="Payment pending", auto_redirect=False, status_code=400)

        _svc().fulfill_payment(ref, provider_payload=status)
        return payment_success_page()

    @app.api_route("/api/payments/pesapal/ipn", methods=["GET", "POST"])
    async def pesapal_ipn(request: Request):
        q = dict(request.query_params)
        ref = str(q.get("OrderMerchantReference") or q.get("orderMerchantReference") or "")
        tracking = str(q.get("OrderTrackingId") or q.get("orderTrackingId") or "")
        if ref and tracking:
            try:
                s = BotSettings.from_env()
                client = PesapalClient(s)
                token, token_err = client.get_token()
                if token and not token_err:
                    code, status = client.get_transaction_status(token, tracking)
                    if code < 300 and "completed" in str((status or {}).get("payment_status_description", "")).lower():
                        _svc().fulfill_payment(ref, provider_payload=status)
            except Exception:
                pass
        return JSONResponse({"success": True})

    @app.post("/api/license/activate")
    async def license_activate(request: Request, payload: ActivatePayload):
        user_id = _require_user_id(request)
        try:
            result = _svc().activate_key_for_user(user_id=user_id, activation_key=payload.activation_key, device_id=payload.device_id)
            return JSONResponse({"success": True, **result})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Activation failed") from exc

    @app.get("/api/license/status")
    async def license_status(request: Request):
        user_id = _require_user_id(request)
        svc = _svc()
        if svc.is_admin_user(user_id):
            return JSONResponse({"active": True, "admin_bypass": True})
        key = request.headers.get("x-activation-key", "").strip()
        device_id = request.headers.get("x-device-id", "").strip()
        if not key:
            return JSONResponse({"active": False})
        return JSONResponse({"active": svc.validate_key_for_user_device(user_id, key, device_id)})

    @app.get("/api/license/subscriptions")
    async def license_subscriptions(request: Request, limit: int = 30):
        user_id = _require_user_id(request)
        return JSONResponse({"items": _svc().list_user_subscriptions(user_id=user_id, limit=limit)})

    @app.get("/api/signals/analytics")
    async def signal_analytics(request: Request):
        _require_user_id(request)
        return JSONResponse(jsonable_encoder(_svc().signal_outcomes_analytics()))

    @app.post("/api/signals/outcomes")
    async def create_signal_outcome(request: Request, payload: SignalOutcomeCreatePayload):
        user_id = _require_user_id(request)
        signal_id = _svc().create_signal_outcome(
            user_id=user_id,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            action=payload.action,
            confidence=payload.confidence,
            outcome=payload.outcome,
        )
        return JSONResponse({"success": True, "signal_id": signal_id})

    @app.post("/api/signals/outcomes/{signal_id}")
    async def update_signal_outcome(request: Request, signal_id: int, payload: SignalOutcomeUpdatePayload):
        user_id = _require_user_id(request)
        ok = _svc().update_signal_outcome(signal_id=signal_id, user_id=user_id, outcome=payload.outcome)
        if not ok:
            raise HTTPException(status_code=404, detail="Signal record not found")
        return JSONResponse({"success": True})

    @app.post("/api/predict")
    async def predict(request: Request, payload: PredictPayload):
        user_id = _require_user_id(request)
        svc = _svc()
        key = request.headers.get("x-activation-key", "").strip()
        device_id = request.headers.get("x-device-id", "").strip()
        if not svc.is_admin_user(user_id) and (not key or not svc.validate_key_for_user_device(user_id, key, device_id)):
            raise HTTPException(status_code=401, detail="Active license required for this account")
        try:
            result = generate_live_prediction(
                BotSettings.from_env(),
                LivePredictionRequest(
                    **payload.model_dump(),
                    ohlcv_limit=180,
                    reddit_limit=25,
                    min_engagement=40,
                    llm_model="gemini-2.0-flash",
                ),
            )
            return JSONResponse(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid request") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Prediction engine failed: {exc}") from exc

    # Admin APIs
    # Admin APIs
    @app.get("/api/admin/overview")
    async def admin_overview(request: Request):
        _require_admin(request)
        return JSONResponse(jsonable_encoder(_svc().admin_overview()))

    @app.get("/api/admin/users")
    async def admin_users(request: Request, limit: int = 200):
        _require_admin(request)
        return JSONResponse(jsonable_encoder({"items": _svc().admin_list_users(limit=limit)}))

    @app.post("/api/admin/users/{user_id}")
    async def admin_patch_user(request: Request, user_id: int, payload: AdminUserPatchPayload):
        _require_admin(request)
        if payload.is_admin is not None:
            _svc().admin_set_user_admin(user_id, payload.is_admin)
        if payload.is_active is not None:
            _svc().admin_set_user_active(user_id, payload.is_active)
        return JSONResponse({"success": True})

    @app.get("/api/admin/payments")
    async def admin_payments(request: Request, limit: int = 300):
        _require_admin(request)
        return JSONResponse(jsonable_encoder({"items": _svc().admin_list_payments(limit=limit)}))

    @app.get("/api/admin/licenses")
    async def admin_licenses(request: Request, limit: int = 300):
        _require_admin(request)
        return JSONResponse(jsonable_encoder({"items": _svc().admin_list_licenses(limit=limit)}))

    @app.post("/api/admin/licenses/{license_id}")
    async def admin_license_action(request: Request, license_id: int, payload: AdminLicenseActionPayload):
        _require_admin(request)
        if payload.action == "revoke":
            _svc().admin_revoke_license(license_id)
        elif payload.action == "clear_device":
            _svc().admin_clear_license_device(license_id)
        return JSONResponse({"success": True})

    @app.get("/api/admin/predictions")
    async def admin_predictions(request: Request, limit: int = 300):
        _require_admin(request)
        return JSONResponse(jsonable_encoder({"items": _svc().admin_list_prediction_runs(limit=limit)}))
    @app.post("/api/admin/backtest/run")
    async def admin_run_backtest(request: Request, payload: AdminBacktestPayload):
        _require_admin(request)
        try:
            out = run_ad_hoc_backtest(
                BotSettings.from_env(),
                AdhocBacktestRequest(**payload.model_dump()),
            )
            return JSONResponse(out)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid request") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}") from exc

    @app.get("/api/admin/model-monitor")
    async def admin_model_monitor(request: Request, limit: int = 300):
        _require_admin(request)
        rows = _svc().admin_list_prediction_runs(limit=limit)
        items = []
        wf_brier_vals = []
        wf_acc_vals = []
        for row in rows:
            payload = row.get("payload_json")
            parsed = {}
            try:
                if isinstance(payload, str):
                    parsed = json.loads(payload)
                elif isinstance(payload, dict):
                    parsed = payload
            except Exception:
                parsed = {}
            quality = parsed.get("model_quality") if isinstance(parsed, dict) else {}
            if not isinstance(quality, dict):
                quality = {}
            wf_acc = float(quality.get("wf_accuracy", 0.0) or 0.0)
            wf_brier = float(quality.get("wf_brier", 0.0) or 0.0)
            wf_trade_rate = float(quality.get("wf_trade_rate", 0.0) or 0.0)
            wf_avg_edge = float(quality.get("wf_avg_edge", 0.0) or 0.0)
            cache_hit = float(quality.get("cache_hit", 0.0) or 0.0)
            if wf_brier > 0:
                wf_brier_vals.append(wf_brier)
            if wf_acc > 0:
                wf_acc_vals.append(wf_acc)
            items.append(
                {
                    "run_id": row.get("id"),
                    "created_at": row.get("created_at"),
                    "market_type": parsed.get("market_type", "crypto"),
                    "symbol": row.get("symbol") or parsed.get("symbol", ""),
                    "timeframe": row.get("timeframe") or parsed.get("timeframe", ""),
                    "signal": parsed.get("signal", ""),
                    "confidence": parsed.get("confidence", row.get("confidence", 0.0)),
                    "accuracy": float(quality.get("accuracy", 0.0) or 0.0),
                    "brier": float(quality.get("brier", 0.0) or 0.0),
                    "wf_accuracy": wf_acc,
                    "wf_brier": wf_brier,
                    "wf_trade_rate": wf_trade_rate,
                    "wf_avg_edge": wf_avg_edge,
                    "cache_hit": cache_hit,
                }
            )

        cache = model_cache_overview()
        overview = {
            "models_in_cache": cache.get("count", 0),
            "cache_ttl_seconds": cache.get("ttl_seconds", 0),
            "recent_runs": len(items),
            "avg_wf_accuracy": round(sum(wf_acc_vals) / len(wf_acc_vals), 6) if wf_acc_vals else 0.0,
            "avg_wf_brier": round(sum(wf_brier_vals) / len(wf_brier_vals), 6) if wf_brier_vals else 0.0,
        }
        return JSONResponse({"overview": overview, "items": items, "cache": cache})
    return app


app = create_app()


def run() -> None:
    import uvicorn

    s = BotSettings.from_env()
    uvicorn.run("cryptobot.webapp:app", host=s.app_host, port=s.app_port, reload=False)


if __name__ == "__main__":
    run()











































