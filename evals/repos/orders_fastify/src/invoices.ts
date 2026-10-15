import express from 'express';

export const invoices = express.Router();

function requireAuth(req: express.Request, res: express.Response, next: express.NextFunction): void {
  if (!req.headers.authorization) {
    res.status(401).end();
    return;
  }
  next();
}

function listInvoices(_req: express.Request, res: express.Response): void {
  res.json([]);
}

function createInvoice(req: express.Request, res: express.Response): void {
  res.status(201).json(req.body);
}

invoices.route('/invoices').get(listInvoices).post(requireAuth, createInvoice);
