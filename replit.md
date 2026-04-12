# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Mockups

- VisionDock SPA mockup lives at `artifacts/mockup-sandbox/src/components/mockups/visiondock/VisionDockSPA.tsx`.
- The mockup is a self-contained React/Tailwind component for a white-background professional business no-code computer vision training platform. The UI is fully Turkish and includes simulated active interactions for navigation, task examples, dataset upload, synthetic data generation, model view/edit/delete/import, GPU cost approval, training start, inference deployment, and an enterprise audit log.

## Artifacts

- VisionDock web implementation lives at `artifacts/visiondock`. It is a React + Vite single-page app built from the selected canvas mockup, using client-side state only. The Turkish UI includes interactive views for Ana Sayfa, Projeler, Model Kütüphanesi, Çıkarım, and Ödeme ve Planlar, with visible audit log updates for key actions.
