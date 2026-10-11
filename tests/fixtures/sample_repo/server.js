const express = require("express");
const app = express();

const requireAuth = (req, res, next) => {
  if (!req.headers.authorization) return res.status(401).end();
  next();
};

function listUsers(req, res) {
  res.json([]);
}

class UserService {
  find(id) {
    return { id };
  }
}

app.get("/users", requireAuth, listUsers);
app.listen(3000);
