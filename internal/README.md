# Internal tools

Not part of the customer-facing product. Lives here to stay out of `web/` and `src/`.

## `analytics/`

A vanilla-JS Chart.js dashboard that hits the backend's `/api/v1/analytics/*` endpoints with an API key. Useful for ops monitoring (pipeline success, grounding rate, risk detections), not something we ship to therapists.

Open `analytics/index.html` directly in a browser, paste an API key + API URL, and connect. Or serve it with any static HTTP server.
