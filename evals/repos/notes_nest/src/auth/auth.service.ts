import * as bcrypt from 'bcrypt';
import * as jwt from 'jsonwebtoken';

const SECRET = process.env.JWT_SECRET ?? 'dev-secret';
const revoked = new Set<string>();

export interface User {
  id: number;
  email: string;
  passwordHash: string;
  role: 'user' | 'admin';
}

const users: User[] = [];

export class AuthService {
  async validateUser(email: string, password: string): Promise<User> {
    const user = users.find((u) => u.email === email);
    if (!user || !(await bcrypt.compare(password, user.passwordHash))) {
      throw new Error('invalid credentials');
    }
    return user;
  }

  async createUser(email: string, password: string): Promise<{ id: number }> {
    const passwordHash = await bcrypt.hash(password, 10);
    const user: User = { id: users.length + 1, email, passwordHash, role: 'user' };
    users.push(user);
    return { id: user.id };
  }

  signToken(user: User): string {
    return jwt.sign({ sub: user.id, role: user.role }, SECRET, { expiresIn: '1h' });
  }

  refreshToken(token: string): string {
    const payload = jwt.verify(token, SECRET) as { sub: number; role: string };
    return jwt.sign({ sub: payload.sub, role: payload.role }, SECRET, { expiresIn: '1h' });
  }

  revokeToken(token: string): { revoked: boolean } {
    revoked.add(token);
    return { revoked: true };
  }

  isRevoked(token: string): boolean {
    return revoked.has(token);
  }
}
