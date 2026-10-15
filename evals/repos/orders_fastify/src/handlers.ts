interface Order {
  id: number;
  total: number;
  status: 'open' | 'cancelled';
}

const orders: Order[] = [];

export async function listOrders(): Promise<Order[]> {
  return orders;
}

export async function getOrder(req: { params: { id: string } }): Promise<Order | undefined> {
  return orders.find((o) => o.id === Number(req.params.id));
}

export async function createOrder(req: { body: { total: number } }): Promise<Order> {
  const order: Order = { id: orders.length + 1, total: req.body.total, status: 'open' };
  orders.push(order);
  return order;
}

export async function cancelOrder(req: { params: { id: string } }): Promise<{ cancelled: boolean }> {
  const order = orders.find((o) => o.id === Number(req.params.id));
  if (order) order.status = 'cancelled';
  return { cancelled: Boolean(order) };
}

export async function statusHandler(): Promise<{ orders: number }> {
  return { orders: orders.length };
}
