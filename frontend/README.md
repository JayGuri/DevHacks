# ARFL Platform
Federated Learning Mission Control Dashboard

## Setup
```bash
npm install
npm run dev    # http://localhost:5173
```

## Demo Accounts (password: `password` for all)
| Email | Role |
|---|---|
| lead@arfl.dev | Team Lead |
| contributor1@arfl.dev | Contributor |
| contributor2@arfl.dev | Contributor |
| contributor3@arfl.dev | Contributor |

## What does what
- **Simple/Detailed toggle**: top-right of every page. Persists across sessions.
- **Team Lead**: full admin including block nodes, change aggregator, export results.
- **Contributor**: own node + read-only server metrics.

## Connecting real data
Replace the `setInterval` in `src/hooks/useFL.js` with a WebSocket.
Map server JSON to `RoundMetrics` shape from `src/lib/mockData.js`.
Call `store.appendRound()` and `store.updateNode()` from the socket handler.
Zero UI changes needed.
