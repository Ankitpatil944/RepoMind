import jwt from 'jsonwebtoken';

const SECRET = process.env.JWT_SECRET ?? 'dev-secret';

export function issueToken(email: string): string {
  return jwt.sign({ sub: email }, SECRET, { expiresIn: '1h' });
}

/** Fastify hook: rejects the request unless it carries a valid bearer token. */
export async function verifyJwt(req: { headers: Record<string, string>; user?: unknown }): Promise<void> {
  const token = (req.headers['authorization'] ?? '').replace(/^Bearer\s+/i, '');
  req.user = jwt.verify(token, SECRET);
}

export async function requireAdmin(req: { user?: { role?: string } }): Promise<void> {
  if (req.user?.role !== 'admin') throw new Error('admin only');
}
