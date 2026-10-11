// MVP hackathon: area Comune protetta da password condivisa (ADMIN_PASSWORD).
// Da sostituire con Supabase Auth + ruolo "operator"/"admin".
export const isAdmin = (req: Request) =>
  !!process.env.ADMIN_PASSWORD && req.headers.get("x-admin-password") === process.env.ADMIN_PASSWORD;
