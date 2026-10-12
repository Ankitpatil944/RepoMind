const express = require("express");
const jwt = require("jsonwebtoken");

const app = express();
const router = express.Router();

function requireAuth(req, res, next) {
  jwt.verify(req.headers.authorization, "secret");
  next();
}

function login(req, res) {
  const token = jwt.sign({ id: 1 }, "secret");
  res.json({ token });
}

function listOrders(req, res) {
  res.json([]);
}

app.post("/api/login", login);
router.use(requireAuth);
router.get("/orders", listOrders);
app.get("/ping", (req, res) => res.send("pong"));
app.get("/me", requireAuth, (req, res) => res.json(req.user));
