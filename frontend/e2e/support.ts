import { execSync } from 'node:child_process';
import { createHmac } from 'node:crypto';
import path from 'node:path';

import { expect, type Page } from '@playwright/test';

export const fullStack = !!process.env.E2E_FULL_STACK;
export const password = 'correct horse battery staple';
const repoRoot = path.resolve(import.meta.dirname, '..', '..');

/** Creates an organization through the operator CLI and returns the admin invitation token. */
export function createOrganization(name: string, adminEmail: string): string {
  const output = execSync(
    `docker compose exec -T api python -m app.cli create-organization --name "${name}" --admin-email ${adminEmail}`,
    { cwd: repoRoot, encoding: 'utf-8' },
  );
  const match = output.match(/\/invite\/([A-Za-z0-9_-]+)/);
  if (!match?.[1]) throw new Error(`No invitation link in: ${output}`);
  return match[1];
}

export async function acceptInvitation(page: Page, token: string, name: string) {
  await page.goto(`/invite/${token}`);
  await page.getByLabel('Full name').fill(name);
  await page.getByLabel('Choose a password').fill(password);
  await page.getByRole('button', { name: /^Join / }).click();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Good morning');
}

/** Reads the newest email to `to` from Mailpit and returns the invitation token in it. */
export async function invitationTokenFromMail(to: string): Promise<string> {
  const mailpit = process.env.MAILPIT_URL ?? 'http://localhost:8025';
  for (let attempt = 0; attempt < 20; attempt++) {
    const search = await fetch(`${mailpit}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`);
    const { messages } = (await search.json()) as { messages: { ID: string }[] };
    if (messages.length > 0) {
      const message = await fetch(`${mailpit}/api/v1/message/${messages[0]!.ID}`);
      const { Text } = (await message.json()) as { Text: string };
      const match = Text.match(/\/invite\/([A-Za-z0-9_-]+)/);
      if (match?.[1]) return match[1];
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`No invitation email to ${to}`);
}

export interface DemoLogins {
  admin: { email: string; password: string };
  planner: { email: string; password: string };
  couple: { email: string; password: string };
}

/** Creates a demo organization with invented data and returns its logins. */
export function seedDemo(name: string): DemoLogins {
  const output = execSync(
    `docker compose exec -T api python -m app.cli seed-demo --name "${name}"`,
    { cwd: repoRoot, encoding: 'utf-8' },
  );
  const login = (role: string) => {
    const match = output.match(new RegExp(`${role}\\s+(\\S+@example\\.com)\\s+/\\s+(\\S+)`));
    if (!match) throw new Error(`No ${role} login in: ${output}`);
    return { email: match[1]!, password: match[2]! };
  };
  return { admin: login('admin'), planner: login('planner'), couple: login('couple') };
}

export async function signIn(page: Page, email: string, secret: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(secret);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** RFC 6238 code (SHA-1, 6 digits, 30 s) for a base32 secret, `offset` steps from now. */
export function totp(secret: string, offset = 0): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const char of secret.replace(/=+$/, '')) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, '0');
  }
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000) + offset));
  const hmac = createHmac('sha1', key).update(counter).digest();
  const start = hmac[hmac.length - 1]! & 0xf;
  const code = (hmac.readUInt32BE(start) & 0x7fffffff) % 1_000_000;
  return String(code).padStart(6, '0');
}
