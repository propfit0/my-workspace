# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A single-page "bucket list" tracker (Korean UI). Vanilla JS, no framework, no build step, no backend — all data lives in the browser's `localStorage`. Built as a personal learning/portfolio project.

## Running the app

There is no build/lint/test tooling in this repo — it's static files. To run it locally, use any static file server, e.g.:

```bash
python -m http.server 8000
# then open http://localhost:8000
```

Or open `index.html` directly in a browser, or use the VS Code "Live Server" extension. There are no npm scripts, package.json, linter, or test suite.

## Architecture

Two-layer separation between data and UI, loaded via plain `<script>` tags in `index.html` (`storage.js` before `app.js`, both attached to `window`):

- **`js/storage.js`** — `BucketStorage`, a stateless data-access object. Every method (`load`, `save`, `addItem`, `updateItem`, `deleteItem`, `toggleComplete`, `getStats`, `getFilteredList`) reads the *entire* list from `localStorage` (key `bucketList`), mutates, and writes it back. There is no in-memory cache — `storage.js` is the single source of truth on disk, and `app.js` never holds list state itself.
- **`js/app.js`** — `BucketListApp`, a class instantiated once as the global `app` on `DOMContentLoaded`. Holds only UI state (`currentFilter`, `editingId`). Every mutation (add/toggle/edit/delete) calls into `BucketStorage` then immediately calls `this.render()`, which re-reads via `getFilteredList()`/`getStats()` and re-generates the entire list's HTML via `innerHTML`. There is no partial/diffed rendering.
- List item buttons (toggle/edit/delete) use inline `onclick="app.handleToggle('...')"` handlers referencing the global `app` instance, rather than addEventListener delegation — this is why `app` must stay a global and why `escapeHtml()` is applied to any title interpolated into that generated HTML.

Data shape (item record):
```js
{ id: "<Date.now() string>", title: string, completed: boolean, createdAt: ISOString, completedAt: ISOString | null }
```

Styling: Tailwind CSS is loaded from the CDN (`cdn.tailwindcss.com`) directly in `index.html` — no Tailwind config file, no build/purge step. `css/styles.css` only adds what Tailwind utility classes can't easily express: keyframe animations (item slide-in, modal fade/scale-in), the `.filter-btn.active` state, and a `prefers-color-scheme: dark` override block.
