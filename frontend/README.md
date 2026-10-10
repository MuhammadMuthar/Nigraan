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
- `/run`: payment run with the cash panel and a preview of what needs attention
- `/flagged`: Flagged invoices, the payment decisions table (blocked / review / allow), search, second approval
- `/cases`, `/cases/[id]`: case detail with evidence
- `/upload`: document reader
- `/cash`: 13-week outlook and scenarios
- `/dashboard`
- `/vendors`

Display preferences live in the floating button (bottom-right by default; drag it anywhere): light, dark or system theme, animations on or off. If you hide it, bring it back with <kbd>Shift</kbd> + <kbd>P</kbd> or from the profile menu. Choices are stored in this browser only.

API responses are cached per path and refreshed in the background, so revisiting a screen renders instantly; hovering a menu item prefetches that screen's data.

See the root [README](../README.md).
