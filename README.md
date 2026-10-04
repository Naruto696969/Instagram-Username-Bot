# Telegram Digital Services Store

An asynchronous storefront for Claimer and Swapper services, built with Python 3.12+, aiogram 3, SQLAlchemy async, and SQLite. The database URL can be changed to PostgreSQL (`postgresql+asyncpg://...`) without changing the models or application services.

## Features

- Inline product catalog with database-backed inventory and USD prices.
- Terms-version acceptance gate before checkout.
- Atomic temporary stock reservations, order expiry, and one-time stock deduction after payment approval.
- SOL, ETH, BTC, and LTC receiving addresses loaded from environment variables.
- Manual transaction-hash review and pluggable blockchain payment providers.
- Per-user order history, payment notifications, and an admin panel protected by Telegram ID allowlisting.
- Admin inventory, price, product enable/disable, order review/search, statistics, and bounded broadcast tools.
- Per-product stock dashboard with atomic, audited stock changes, explicit sales availability, product removal confirmation, and customer stock alerts.
- Unique transaction-hash constraint, request validation, callback ownership checks, rate limiting, and audit records.

## Install and run

Requires Python 3.12 or later and a Telegram bot token from BotFather.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `BOT_TOKEN`, at least one numeric Telegram ID in `ADMIN_IDS`, and the receiving wallet addresses in `.env`. Then start the bot:

```powershell
python -m bot.main
```

The first run creates `bot.db` and seeds the three configured catalog products. Inventory starts at zero and can be entered under `/admin` → **Manage Stock**. Do not check `.env`, database files, API keys, or wallet secrets into source control.

Run the async service tests with:

```powershell
python -m unittest discover -v
```

## Payment modes

### Manual approval (default)

Keep `MANUAL_PAYMENT_APPROVAL=true`. The customer submits a transaction hash; it moves the order to `payment_detected` and alerts administrators. An allowlisted admin must approve or reject it. A submitted hash is never treated as proof of payment.

### Blockchain verification

Set `MANUAL_PAYMENT_APPROVAL=false` and configure a price API URL plus blockchain endpoints. The customer submits a hash and uses **Check Payment**. The relevant provider checks the destination, amount, and configured confirmation threshold before the bot approves the payment. BTC uses a mempool.space-compatible API by default. LTC requires a Litecoin mempool.space-compatible API URL. ETH requires a JSON-RPC endpoint; SOL requires a Solana JSON-RPC endpoint. Public/free APIs can have rate limits and should be replaced with reliable provider endpoints for production.

`CRYPTO_PRICE_API_URL` expects a CoinGecko-compatible `/simple/price` response. For example, with the default API shape the bot requests `ids=<coin>&vs_currencies=usd`. Automatic verification is disabled for an order if no crypto/USD quote can be obtained. When choosing a provider, validate the network and API endpoint yourself before accepting customer funds.

**Important:** The included blockchain adapters are initial integrations, not a substitute for independent payment reconciliation and operational monitoring. In particular, SOL verification handles parsed native SOL transfer instructions, not SPL token payments. Use manual review until the configured endpoint, chain/network, address parsing, and confirmation policy have been independently tested for your deployment. The bot never requests or stores private keys, seed phrases, or wallet passwords.

## Admin operations

Only IDs listed in `ADMIN_IDS` can use `/admin` or admin callbacks. Add stock before opening the store. **Manage Stock** shows each product's stock, reserved units, price, and purchasability controls. Stock quantity and the admin's sales-enabled setting are separate: zero available units always displays SOLD OUT, while adding inventory resumes sales only if sales were not manually disabled. Sold-out customer pages include a one-time **Notify Me** alert. Product deletion requires confirmation, blocks products with reserved orders, removes the product and its inventory from the storefront, and retains its database row so historical orders remain readable. Price changes require explicit confirmation. Payment approvals, rejects, order status changes, every inventory/availability change, product removals, and broadcasts are audit logged. Keep the admin list short and protect those Telegram accounts with strong account security.

Terms are controlled by `TERMS_TEXT` and `TERMS_VERSION`. Update the version whenever terms materially change; users must accept the current version before creating another order.

## Database and deployment notes

- SQLite is intended for development/single-instance deployments. Configure PostgreSQL with `DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database` for concurrent production workloads.
- To deploy on Render, push this project to a GitHub repository, create a Render Blueprint from that repository, and apply `render.yaml`. The blueprint creates a paid persistent PostgreSQL instance and a paid always-on background worker. Enter the BotFather token, Telegram admin IDs, wallet receiving addresses, and support username in Render's prompted secret/environment fields. Do not commit a real `.env` file. Once deployed, open the worker's logs, confirm it starts polling, then message the bot and initialize stock through `/admin`.
- Render PostgreSQL connection strings (`postgres://` and `postgresql://`) are automatically adapted to SQLAlchemy's async `postgresql+asyncpg://` driver.
- Render deployment is not automatic from this workspace: the project must first be pushed to a GitHub repository and connected to your Render account. The bot token and other private deployment settings must be entered directly in Render.
- SQLite schema initialization uses `create_all`; use versioned migrations (for example Alembic) before evolving a live production schema.
- Order reservations expire after `ORDER_EXPIRY_MINUTES`. Orders with a submitted hash remain reserved for manual review rather than silently expiring.
- `RATE_LIMIT_PER_MINUTE` is an in-process limiter; use a shared limiter and webhook/process coordination when running multiple replicas.
- Configure log collection, database backups, alerting, and recovery procedures before production launch.

## Project layout

```text
bot/
  config.py
  main.py
  database/       # SQLAlchemy models, async session, repository helpers
  handlers/       # Store, checkout, payments, orders, support, admin
  keyboards/
  middlewares/
  payments/       # Verification protocol and currency providers
  services/       # Inventory, orders, payment quotes
  utils/
```
