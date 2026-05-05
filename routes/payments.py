"""
PAYMENT MODULE - routes/payments.py
All payment API endpoints live here.

Endpoints:
  POST /payments/create     → Create a payment intent (get a client_secret)
  POST /payments/confirm    → Confirm/charge the payment
  GET  /payments/{id}       → Check payment status
  POST /payments/webhook    → Stripe calls this to tell us payment succeeded/failed
  GET  /payments/history    → List all payments (for admin/testing)
"""

import stripe
import os
from dotenv import load_dotenv

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel
from database.db import SessionLocal
from database import models
from datetime import datetime
from database.db import SessionLocal
from database.models import Transaction


load_dotenv()

router = APIRouter()

# Set Stripe secret key from .env
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


# ─────────────────────────────────────────────
# REQUEST BODY SCHEMAS (what the API expects)
# ─────────────────────────────────────────────

class CreatePaymentRequest(BaseModel):
    order_id: str           # ID from the Order Module
    amount: int             # Amount in paise (e.g. 50000 = ₹500) — always use smallest unit
    currency: str = "inr"   # Default to INR
    customer_email: str     # Customer's email

class ConfirmPaymentRequest(BaseModel):
    payment_intent_id: str  # The ID returned from /create


# ─────────────────────────────────────────────
# ENDPOINT 1: CREATE PAYMENT
# Called by: Order Module when user clicks "Pay"
# Returns: client_secret (frontend uses this to show payment form)
# ─────────────────────────────────────────────

@router.post("/create")
def create_payment(data: CreatePaymentRequest):
    # Security: validate amount is positive
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    try:
        # Create a PaymentIntent in Stripe
        intent = stripe.PaymentIntent.create(
            amount=data.amount,
            currency=data.currency,
            metadata={
                "order_id": data.order_id,
                "customer_email": data.customer_email
            }
        )

        # Save to our database
        db = SessionLocal()
        transaction = models.Transaction(
            payment_intent_id=intent.id,
            order_id=data.order_id,
            amount=data.amount,
            currency=data.currency,
            customer_email=data.customer_email,
            status="created",
            created_at=datetime.utcnow()
        )
        db.add(transaction)
        db.commit()
        db.close()

        return {
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,   # Frontend needs this
            "amount": data.amount,
            "currency": data.currency,
            "status": "created"
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")


# ─────────────────────────────────────────────
# ENDPOINT 2: CONFIRM PAYMENT
# Called by: Frontend after user enters card details
# ─────────────────────────────────────────────

@router.post("/confirm")
def confirm_payment(data: ConfirmPaymentRequest):
    try:
        # Ask Stripe for latest status of this payment
        intent = stripe.PaymentIntent.retrieve(data.payment_intent_id)

        # Update in our database
        db = SessionLocal()
        transaction = db.query(models.Transaction).filter(
            models.Transaction.payment_intent_id == data.payment_intent_id
        ).first()

        if not transaction:
            db.close()
            raise HTTPException(status_code=404, detail="Payment not found in database")

        transaction.status = intent.status
        transaction.updated_at = datetime.utcnow()
        db.commit()
        db.close()

        return {
            "payment_intent_id": intent.id,
            "status": intent.status,
            "amount": intent.amount,
            "currency": intent.currency
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")


# ─────────────────────────────────────────────
# ENDPOINT 3: GET PAYMENT STATUS
# Called by: Order Module or Rider Module to check if payment is done
# ─────────────────────────────────────────────

@router.get("/{payment_intent_id}")
def get_payment_status(payment_intent_id: str):
    db = SessionLocal()
    transaction = db.query(models.Transaction).filter(
        models.Transaction.payment_intent_id == payment_intent_id
    ).first()
    db.close()

    if not transaction:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "payment_intent_id": transaction.payment_intent_id,
        "order_id": transaction.order_id,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "status": transaction.status,
        "customer_email": transaction.customer_email,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at
    }


# ─────────────────────────────────────────────
# ENDPOINT 4: STRIPE WEBHOOK
# Called by: Stripe automatically when payment succeeds or fails
# This is the MOST important endpoint — never rely only on frontend confirmation!
# ─────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        # Verify the webhook is actually from Stripe (security check)
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature — not from Stripe")

    # Handle different event types
    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        _update_transaction_status(intent["id"], "succeeded")
        print(f"✅ Payment succeeded: {intent['id']}")

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        _update_transaction_status(intent["id"], "failed")
        print(f"❌ Payment failed: {intent['id']}")

    return {"status": "webhook received"}


# ─────────────────────────────────────────────
# ENDPOINT 5: LIST ALL PAYMENTS (for testing/admin)
# ─────────────────────────────────────────────

@router.get("/")
def list_payments(limit: int = 20):
    db = SessionLocal()
    transactions = db.query(models.Transaction).order_by(
        models.Transaction.created_at.desc()
    ).limit(limit).all()
    db.close()

    return [
        {
            "payment_intent_id": t.payment_intent_id,
            "order_id": t.order_id,
            "amount": t.amount,
            "currency": t.currency,
            "status": t.status,
            "customer_email": t.customer_email,
            "created_at": t.created_at
        }
        for t in transactions
    ]


# ─────────────────────────────────────────────
# HELPER FUNCTION (not an endpoint)
# ─────────────────────────────────────────────

def _update_transaction_status(payment_intent_id: str, status: str):
    """Updates transaction status in DB — used by webhook handler"""
    db = SessionLocal()
    transaction = db.query(models.Transaction).filter(
        models.Transaction.payment_intent_id == payment_intent_id
    ).first()
    if transaction:
        transaction.status = status
        transaction.updated_at = datetime.utcnow()
        db.commit()
    db.close()
