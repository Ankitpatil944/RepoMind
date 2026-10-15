import crypto from 'crypto';
import express, { NextFunction, Request, Response } from 'express';

const app = express();
app.use(express.json());

/** Reject calls whose HMAC-SHA256 signature does not match the shared secret. */
function verifySignature(req: Request, res: Response, next: NextFunction): void {
  const expected = crypto
    .createHmac('sha256', process.env.WEBHOOK_SECRET ?? '')
    .update(JSON.stringify(req.body))
    .digest('hex');
  if (req.header('x-signature') !== expected) {
    res.status(401).json({ error: 'bad signature' });
    return;
  }
  next();
}

export function handleEmailEvent(req: Request, res: Response): void {
  res.json({ received: req.body?.type ?? 'unknown' });
}

app.post('/webhooks/email', verifySignature, handleEmailEvent);
app.get('/webhooks/ping', (_req: Request, res: Response) => res.json({ pong: true }));

app.listen(Number(process.env.PORT ?? 4000));
