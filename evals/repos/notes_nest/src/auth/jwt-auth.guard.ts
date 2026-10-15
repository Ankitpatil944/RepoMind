import * as jwt from 'jsonwebtoken';

const SECRET = process.env.JWT_SECRET ?? 'dev-secret';

/** Rejects requests without a valid `Authorization: Bearer <jwt>` header. */
export class JwtAuthGuard {
  canActivate(request: { headers: Record<string, string>; user?: unknown }): boolean {
    const header = request.headers['authorization'] ?? '';
    const token = header.replace(/^Bearer\s+/i, '');
    if (!token) return false;
    try {
      request.user = jwt.verify(token, SECRET);
      return true;
    } catch {
      return false;
    }
  }
}
