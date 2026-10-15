import Fastify from 'fastify';
import { requireAdmin, verifyJwt } from './auth';
import { cancelOrder, createOrder, getOrder, listOrders, statusHandler } from './handlers';

export const app = Fastify({ logger: true });

app.addHook('onRequest', async (req) => {
  (req as { startedAt?: number }).startedAt = Date.now();
});

app.get('/health', async () => ({ ok: true }));

app.post('/auth/login', async (req, reply) => {
  const { email } = req.body as { email: string };
  return reply.send({ token: await import('./auth').then((m) => m.issueToken(email)) });
});

app.get('/orders', { preHandler: [verifyJwt] }, listOrders);
app.get('/orders/:id', { onRequest: verifyJwt }, getOrder);
app.post('/orders', { preHandler: verifyJwt, schema: { body: { type: 'object' } } }, createOrder);

app.route({
  method: 'DELETE',
  url: '/orders/:id',
  preHandler: [verifyJwt, requireAdmin],
  handler: cancelOrder,
});

app.route({ method: ['GET', 'HEAD'], url: '/public/status', handler: statusHandler });

void app.listen({ port: Number(process.env.PORT ?? 3000) });
