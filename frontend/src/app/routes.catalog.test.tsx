/**
 * Keeps catalog/discovered/frontend-routes.json in step with the router. The feature catalog
 * (tools/feature_catalog) reads this file. Regenerate after changing routes:
 *
 *   UPDATE_SNAPSHOTS=1 npx vitest run src/app/routes.catalog.test.tsx
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { isValidElement, type ReactElement, type ReactNode } from 'react';
import type { RouteObject } from 'react-router';
import { describe, expect, it } from 'vitest';

import { routes } from './router';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../../..');
const SNAPSHOT = resolve(ROOT, 'catalog/discovered/frontend-routes.json');
const ROUTER = resolve(HERE, 'router.tsx');

interface DiscoveredRoute {
  path: string;
  component: string;
  file: string | null;
  guard: string | null;
}

function componentName(element: ReactNode): string {
  if (!isValidElement(element)) return '';
  const type = (element as ReactElement).type as { name?: string; displayName?: string } | string;
  return typeof type === 'string' ? type : (type.displayName ?? type.name ?? '');
}

/** Maps imported component names to repository paths, from the router's import lines. */
function importFiles(): Map<string, string> {
  const source = readFileSync(ROUTER, 'utf-8');
  const files = new Map<string, string>();
  for (const match of source.matchAll(/import\s*\{([^}]*)\}\s*from\s*'([^']+)'/g)) {
    const [, names = '', from = ''] = match;
    let path: string | null = null;
    if (from.startsWith('@/')) path = `frontend/src/${from.slice(2)}.tsx`;
    else if (from.startsWith('./')) path = `frontend/src/app/${from.slice(2)}.tsx`;
    if (!path) continue;
    for (const name of names.split(',')) {
      const clean = name.trim();
      if (clean) files.set(clean, path);
    }
  }
  return files;
}

function flatten(list: RouteObject[], prefix: string, guard: string | null): DiscoveredRoute[] {
  const files = importFiles();
  const result: DiscoveredRoute[] = [];
  for (const route of list) {
    const joined = route.index
      ? prefix || '/'
      : route.path?.startsWith('/')
        ? route.path
        : `${prefix}/${route.path ?? ''}`;
    let element: ReactNode = route.element;
    let ownGuard = guard;
    // `<RequireTeam><PlannerLayout /></RequireTeam>`: the guard protects every child route.
    const outer = componentName(element);
    if (outer.startsWith('Require') && isValidElement(element)) {
      ownGuard = outer;
      element = (element as ReactElement<{ children?: ReactNode }>).props.children;
    }
    const component = componentName(element);
    if (route.children) {
      result.push(...flatten(route.children, joined, ownGuard));
    } else {
      result.push({
        path: joined,
        component,
        file: files.get(component) ?? null,
        guard: ownGuard,
      });
    }
  }
  return result;
}

describe('catalog export', () => {
  it('keeps catalog/discovered/frontend-routes.json current', () => {
    const data = {
      generatedBy: 'frontend/src/app/routes.catalog.test.tsx',
      routes: flatten(routes, '', null).sort((a, b) => a.path.localeCompare(b.path)),
    };
    expect(data.routes.length).toBeGreaterThan(30);
    const text = `${JSON.stringify(data, null, 2)}\n`;
    if (process.env.UPDATE_SNAPSHOTS === '1') {
      mkdirSync(dirname(SNAPSHOT), { recursive: true });
      writeFileSync(SNAPSHOT, text, 'utf-8');
    }
    expect(existsSync(SNAPSHOT), 'Run with UPDATE_SNAPSHOTS=1').toBe(true);
    expect(readFileSync(SNAPSHOT, 'utf-8'), 'Out of date: run with UPDATE_SNAPSHOTS=1').toBe(text);
  });
});
