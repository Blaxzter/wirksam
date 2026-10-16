#!/usr/bin/env node

/**
 * Start the whole local dev stack from one terminal:
 *
 *   1. Postgres + Adminer in Docker (waits until the DB is healthy)
 *   2. Alembic migrations
 *   3. Dev login + demo data (`just seed`, a no-op once they exist)
 *   4. Backend (uvicorn --reload) and frontend (vite) side by side, with
 *      their output interleaved and prefixed
 *
 * Ctrl+C stops backend and frontend; the DB container keeps running so the
 * next start is instant (`docker compose stop db adminer` to stop it).
 *
 * Flags:
 *   --no-migrate   skip `alembic upgrade head`
 *   --no-seed      skip the demo seed
 *
 * Everything is served on http://wirksam.localhost (browsers resolve any
 * *.localhost name to loopback, no hosts-file entry needed) on two fixed,
 * deliberately obscure ports, so other projects holding 5555/8787 never get in
 * the way. Frontend and backend share the host so the refresh cookie stays
 * same-site. The Docker and E2E stacks keep 5555/8787 on plain localhost:
 * Node can't resolve *.localhost on Windows, so the E2E helpers can't use it.
 */

import { execSync, spawn } from 'node:child_process';
import net from 'node:net';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..');
const HOST = 'wirksam.localhost';
const FRONTEND_PORT = 47300;
const BACKEND_PORT = 47301;
const FRONTEND_URL = `http://${HOST}:${FRONTEND_PORT}`;
const BACKEND_URL = `http://${HOST}:${BACKEND_PORT}`;
const IS_WINDOWS = process.platform === 'win32';

const args = new Set(process.argv.slice(2));
const migrate = !args.has('--no-migrate');
const seed = !args.has('--no-seed');

// ── Helpers ──────────────────────────────────────────────────────────

function run(cmd) {
    console.log(`  $ ${cmd}`);
    execSync(cmd, { stdio: 'inherit', cwd: REPO_ROOT });
}

/** Resolve true if something is already listening on `port`. */
function portInUse(port) {
    return new Promise((done) => {
        const socket = net.connect({ port, host: '127.0.0.1' });
        socket.once('connect', () => { socket.destroy(); done(true); });
        socket.once('error', () => done(false));
    });
}

const COLORS = { backend: '\x1b[36m', frontend: '\x1b[35m' };
const RESET = '\x1b[0m';

/** Prefix every line of a stream with a coloured label. */
function pipeWithPrefix(stream, label, out) {
    const prefix = `${COLORS[label]}[${label.padEnd(8)}]${RESET} `;
    let buffered = '';
    stream.on('data', (chunk) => {
        buffered += chunk.toString();
        const lines = buffered.split(/\r?\n/);
        buffered = lines.pop();
        for (const line of lines) out.write(prefix + line + '\n');
    });
    stream.on('end', () => { if (buffered) out.write(prefix + buffered + '\n'); });
}

const children = [];

function start(label, cmd, cmdArgs, env = {}) {
    // One command string rather than (cmd, args): pnpm is a .cmd shim on
    // Windows and needs a shell, and Node deprecates shell + an args array.
    // Every argument here is a fixed token without spaces, so joining is safe.
    const child = spawn([cmd, ...cmdArgs].join(' '), {
        cwd: REPO_ROOT,
        env: { ...process.env, FORCE_COLOR: '1', ...env },
        shell: true,
        detached: !IS_WINDOWS, // own process group, so shutdown can kill the tree
    });
    pipeWithPrefix(child.stdout, label, process.stdout);
    pipeWithPrefix(child.stderr, label, process.stderr);
    child.on('exit', (code, signal) => {
        if (shuttingDown) return;
        console.error(`\n${label} exited (${signal ?? code}) — stopping the rest.`);
        shutdown(code ?? 1);
    });
    children.push(child);
}

let shuttingDown = false;

function shutdown(exitCode = 0) {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const child of children) {
        if (child.exitCode !== null) continue;
        // The PID is the shell wrapper; /T takes the uvicorn/vite processes
        // underneath it down too.
        if (IS_WINDOWS) {
            try { execSync(`taskkill /PID ${child.pid} /T /F`, { stdio: 'ignore' }); } catch { /* already gone */ }
        } else {
            try { process.kill(-child.pid, 'SIGTERM'); } catch { /* already gone */ }
        }
    }
    process.exit(exitCode);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

// ── Main ─────────────────────────────────────────────────────────────

for (const [name, port] of [['frontend', FRONTEND_PORT], ['backend', BACKEND_PORT]]) {
    if (await portInUse(port)) {
        console.error(`Port ${port} (${name}) is already in use — is \`just dev\` already running in another terminal?`);
        process.exit(1);
    }
}

console.log('\n▶ Starting Postgres + Adminer...');
run('docker compose up db adminer -d --wait');

if (migrate) {
    console.log('\n▶ Running migrations...');
    run('uv run --directory backend alembic upgrade head');
}

if (seed) {
    console.log('\n▶ Seeding dev login + demo data...');
    run('uv run --directory backend python -m app.scripts.seed_demo');
}

console.log(`\n▶ Frontend ${FRONTEND_URL}`);
console.log(`▶ Backend  ${BACKEND_URL}  (docs: ${BACKEND_URL}/docs)`);
console.log('  Ctrl+C to stop\n');

// uvicorn directly rather than `fastapi dev`: the latter's banner crashes on a
// cp1252 Windows console, and PYTHONIOENCODING covers the app's own logging.
start(
    'backend',
    'uv',
    ['run', '--directory', 'backend', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1', '--port', String(BACKEND_PORT),
        '--reload', '--reload-dir', 'app'],
    // FRONTEND_HOST is also what CORS allows and where email links point.
    { PYTHONIOENCODING: 'utf-8', FRONTEND_HOST: FRONTEND_URL },
);
start(
    'frontend',
    'pnpm',
    ['--prefix', 'frontend', 'dev', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT), '--strictPort'],
    { VITE_API_URL: `${BACKEND_URL}/api/v1` },
);
