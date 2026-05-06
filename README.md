Payment Module — Food Delivery System
> **Part of a class project** building a microservices-based food delivery system.  
> This module handles all payment processing using [Stripe](https://stripe.com) and is deployed independently so other modules (Order, Restaurant, Dispatch) can call it over HTTP.
---
What This Module Does
When a user places an order in the food delivery app, this service:
Creates a payment intent with Stripe (reserves the charge)
Returns a `client_secret` to the frontend so the user can enter card details
Confirms the payment status after the user pays
Stores every transaction in a local SQLite database
Exposes a status endpoint so other modules know whether payment succeeded
It does not handle card details directly — those go straight from the browser to Stripe. This module never sees raw card numbers.
---
Project Structure
```
├── main.py               # FastAPI app entry point
├── routes/
│   └── payments.py       # All payment endpoints
├── database/
│   ├── db.py             # SQLAlchemy engine + session setup
│   └── models.py         # Transaction table schema
├── requirements.txt
├── Procfile.txt          # For Render deployment
└── .env                  # Secret keys (never commit this)
```
---
How Payments Flow
```
User taps "Pay"
      │
      ▼
Order Module ──POST /payments/create──► Payment Module ──► Stripe creates PaymentIntent
                                              │
                                        saves to DB (status: "created")
                                              │
                                        returns client_secret
                                              │
                                      Frontend shows card form
                                              │
                                      User enters card → Stripe charges
                                              │
                              Frontend ──POST /payments/confirm──► Payment Module
                                              │
                                        asks Stripe for status
                                        updates DB (status: "succeeded")
                                              │
                              Restaurant/Rider ──GET /payments/{id}──► checks status
```
---
API Endpoints
`POST /payments/create`
Called by the Order Module when the user clicks Pay.
Request body:
```json
{
  "order_id": "ORD-123",
  "amount": 50000,
  "currency": "inr",
  "customer_email": "user@example.com"
}
```
> `amount` is in **paise** — smallest unit. ₹500 = `50000`
Response:
```json
{
  "payment_intent_id": "pi_3abc...",
  "client_secret": "pi_3abc..._secret_...",
  "amount": 50000,
  "currency": "inr",
  "status": "created"
}
```
---
`POST /payments/confirm`
Called by the frontend after the user submits their card details.
Request body:
```json
{
  "payment_intent_id": "pi_3abc..."
}
```
Response:
```json
{
  "payment_intent_id": "pi_3abc...",
  "status": "succeeded",
  "amount": 50000,
  "currency": "inr"
}
```
---
`GET /payments/{payment_intent_id}`
Called by other modules (Restaurant, Rider/Dispatch) to check if payment is done before proceeding.
Response:
```json
{
  "payment_intent_id": "pi_3abc...",
  "order_id": "ORD-123",
  "amount": 50000,
  "currency": "inr",
  "status": "succeeded",
  "customer_email": "user@example.com",
  "created_at": "2025-01-01T10:00:00",
  "updated_at": "2025-01-01T10:01:00"
}
```
---
`GET /payments/`
Lists recent transactions. Useful for testing and admin review.
Query param: `?limit=20` (default)
---
`POST /payments/webhook` (optional — for production)
Stripe calls this automatically when a payment succeeds or fails. Ensures the database stays in sync even if the frontend crashes mid-payment. Not required for the class demo.
---
Running Locally
1. Clone and install dependencies
```bash
git clone https://github.com/Shree-2005/Cloudproj.git
cd Cloudproj
pip install -r requirements.txt
```
2. Set up environment variables
Create a `.env` file in the root:
```dotenv
STRIPE_SECRET_KEY=sk_test_your_key_here
DATABASE_URL=sqlite:///./test.db
```
> Get a free test key at [dashboard.stripe.com](https://dashboard.stripe.com) → Developers → API Keys
3. Start the server
```bash
uvicorn main:app --reload
```
4. Open the auto-generated docs
```
http://localhost:8000/docs
```
You can test every endpoint directly from the browser here.
---
Testing with Stripe Test Cards
Since this uses Stripe's test mode, no real money is ever charged. Use these card numbers:
Card Number	Scenario
`4242 4242 4242 4242`	Payment succeeds
`4000 0000 0000 9995`	Payment declined
`4000 0025 0000 3155`	Requires authentication
Use any future expiry date, any 3-digit CVV, any billing ZIP.
---
Integration Guide (for other modules)
Order Module — create a payment
```python
import requests

res = requests.post("https://your-render-url.onrender.com/payments/create", json={
    "order_id": "ORD-123",
    "amount": 50000,
    "currency": "inr",
    "customer_email": "user@example.com"
})
client_secret = res.json()["client_secret"]
# Pass this to the frontend to show the Stripe payment form
```
Restaurant / Rider Module — check payment before proceeding
```python
import requests

res = requests.get("https://cloudproj-9b9k.onrender.com/payments/pi_3abc...")
status = res.json()["status"]

if status == "succeeded":
    # proceed with order preparation / rider assignment
```
---
Tech Stack
Layer	Technology
Framework	FastAPI
Database	SQLite + SQLAlchemy
Payments	Stripe API
Deployment	Render
Language	Python 3
---
Team
Built as part of a microservices food delivery system class project.
