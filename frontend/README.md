# Nigraan frontend

Next.js 16 (App Router) + TypeScript + Tailwind 4, with shadcn-style components on Radix, Recharts and react-force-graph-2d. It is a client-rendered app talking to the FastAPI backend.

```bash
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev          # http://localhost:3000
npm run build && npm start
npx playwright test  # happy-path e2e; starts the API and the built app if they are not running
```

Screens:
- `/run`: payment run with the cash panel
- `/cases`, `/cases/[id]`: case detail with evidence
- `/upload`: document reader
- `/cash`: 13-week outlook and scenarios
- `/dashboard`
- `/vendors`

See the root [README](../README.md).
