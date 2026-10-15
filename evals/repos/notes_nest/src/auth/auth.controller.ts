import { Body, Controller, Post, UseGuards } from '@nestjs/common';
import { AuthService } from './auth.service';
import { JwtAuthGuard } from './jwt-auth.guard';

@Controller('auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  /** Exchange email + password for an access token. */
  @Post('login')
  async login(@Body() body: { email: string; password: string }) {
    const user = await this.auth.validateUser(body.email, body.password);
    return { accessToken: this.auth.signToken(user) };
  }

  @Post('register')
  async register(@Body() body: { email: string; password: string }) {
    return this.auth.createUser(body.email, body.password);
  }

  @UseGuards(JwtAuthGuard)
  @Post('refresh')
  refresh(@Body() body: { token: string }) {
    return { accessToken: this.auth.refreshToken(body.token) };
  }

  @UseGuards(JwtAuthGuard)
  @Post('logout')
  logout(@Body() body: { token: string }) {
    return this.auth.revokeToken(body.token);
  }
}
