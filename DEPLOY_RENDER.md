# Render Deployment Guide (CryptoTool)

## 1) Prerequisites
- A GitHub/GitLab/Bitbucket repo with this project pushed.
- External MySQL database (Render currently does not provision MySQL in this blueprint).
- Your provider credentials ready (Gemini, Google OAuth, SMTP, Pesapal, Paystack).

## 2) Blueprint file
- This repo now includes `render.yaml`.
- In Render Dashboard: New > Blueprint > select your repo.

## 3) Required environment values in Render
Set these in Render service environment:
- `APP_BASE_URL` = your public Render URL, e.g. `https://cryptobot-live.onrender.com`
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`
- `GEMINI_API_KEY`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `PESAPAL_CONSUMER_KEY`, `PESAPAL_CONSUMER_SECRET`, `PESAPAL_CALLBACK_URL`, `PESAPAL_IPN_URL`
- `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_WEBHOOK_SECRET`, `PAYSTACK_CALLBACK_URL`
- `ADMIN_EMAILS`

## 4) Callback/OAuth URLs
Replace `<BASE_URL>` with your Render URL.

Google OAuth:
- `GOOGLE_REDIRECT_URI = <BASE_URL>/auth/google/callback`

Pesapal:
- `PESAPAL_CALLBACK_URL = <BASE_URL>/billing/pesapal/callback`
- `PESAPAL_IPN_URL = <BASE_URL>/api/payments/pesapal/ipn`

Paystack:
- `PAYSTACK_CALLBACK_URL = <BASE_URL>/billing/paystack/callback`
- Webhook endpoint in Paystack dashboard: `<BASE_URL>/api/payments/paystack/webhook`

## 5) Start/health
- Start command uses Uvicorn on `$PORT`.
- Health check path is `/api/health`.

## 6) Post-deploy verification
1. Open `<BASE_URL>/api/health` and confirm `{ "status": "ok" }`.
2. Sign up/login test.
3. Google login callback test.
4. Forgot password test.
5. Checkout + callback test.
6. Activation + prediction test.
