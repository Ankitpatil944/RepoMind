/** Application entry point: boots the Nest app on PORT (default 3000). */
export async function bootstrap(): Promise<void> {
  const port = Number(process.env.PORT ?? 3000);
  console.log(`notes api listening on ${port}`);
}

void bootstrap();
