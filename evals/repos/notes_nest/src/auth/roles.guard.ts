/** Allows the request only when the authenticated user has the required role. */
export class RolesGuard {
  constructor(private readonly required: string) {}

  canActivate(request: { user?: { role?: string } }): boolean {
    return request.user?.role === this.required;
  }
}
