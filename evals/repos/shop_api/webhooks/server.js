// Receives payment-provider webhooks and flips order state.
const crypto = require("crypto");
const express = require("express");

const app = express();
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "whsec_dev";

function verifyStripeSignature(req, res, next) {
  const expected = crypto
    .createHmac("sha256", WEBHOOK_SECRET)
    .update(req.rawBody || "")
    .digest("hex");
  if (req.headers["x-signature"] !== expected) {
    return res.status(400).send("bad signature");
  }
  next();
}

function handleStripeEvent(req, res) {
  const event = req.body;
  if (event.type === "charge.succeeded") {
    markOrderPaid(event.data.order_id);
  }
  res.json({ received: true });
}

function markOrderPaid(orderId) {
  console.log("order paid", orderId);
}

app.post("/webhooks/stripe", verifyStripeSignature, handleStripeEvent);
app.get("/webhooks/health", (req, res) => res.send("ok"));

app.listen(4000);
