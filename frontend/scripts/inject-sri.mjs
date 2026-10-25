import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, '..', 'dist');
const indexPath = path.join(distDir, 'index.html');

if (!fs.existsSync(indexPath)) {
  console.log(`SRI injection skipped: ${indexPath} not found.`);
  process.exit(0);
}

let html = fs.readFileSync(indexPath, 'utf-8');
let modified = false;

function computeSriHash(filepath) {
  const content = fs.readFileSync(filepath);
  const hash = crypto.createHash('sha384').update(content).digest('base64');
  return `sha384-${hash}`;
}

html = html.replace(/<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/g, (match, src) => {
  const cleanSrc = src.replace(/^\/+/, '');
  const assetPath = path.join(distDir, cleanSrc);
  if (fs.existsSync(assetPath)) {
    const sri = computeSriHash(assetPath);
    modified = true;
    const cleanTag = match.replace(/\/?>$/, '');
    return `${cleanTag} integrity="${sri}" crossorigin="anonymous">`;
  }
  return match;
});

html = html.replace(/<link\b[^>]*\bhref=["']([^"']+\.css)["'][^>]*>/g, (match, href) => {
  const cleanHref = href.replace(/^\/+/, '');
  const assetPath = path.join(distDir, cleanHref);
  if (fs.existsSync(assetPath)) {
    const sri = computeSriHash(assetPath);
    modified = true;
    const cleanTag = match.replace(/\/?>$/, '');
    return `${cleanTag} integrity="${sri}" crossorigin="anonymous">`;
  }
  return match;
});

if (modified) {
  fs.writeFileSync(indexPath, html, 'utf-8');
  console.log('Successfully injected W3C Subresource Integrity (SRI) hashes into dist/index.html');
}

