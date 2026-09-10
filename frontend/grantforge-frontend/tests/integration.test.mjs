import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appSource = fs.readFileSync(path.resolve(__dirname, "../src/App.jsx"), "utf8");
const htmlSource = fs.readFileSync(path.resolve(__dirname, "../index.html"), "utf8");
const vercelSource = fs.readFileSync(path.resolve(__dirname, "../vercel.json"), "utf8");
const robotsSource = fs.readFileSync(path.resolve(__dirname, "../public/robots.txt"), "utf8");

test("soft-launch site has no active checkout creation flow", () => {
  assert.equal(appSource.includes("createCheckoutSession"), false);
  assert.equal(appSource.includes("Pay Now"), false);
  assert.equal(appSource.includes("$2,500"), false);
  assert.ok(appSource.includes("No payment is collected on this preview"));
  assert.ok(appSource.includes("Online checkout is paused"));
});

test("prior paid checkout returns preserve legacy fulfillment", () => {
  assert.ok(appSource.includes("createDownloadToken"));
  assert.ok(appSource.includes("receiptByToken"));
  assert.ok(appSource.includes("downloadUrlByToken"));
  assert.ok(appSource.includes("new URLSearchParams(window.location.search).get(\"ref\")"));
  assert.ok(appSource.includes("Complete your existing delivery"));
});

test("planned pricing matches the approved pilot model", () => {
  for (const price of ["$9.99", "$49.99", "$99.99", "$199.99"]) {
    assert.ok(appSource.includes(price), `missing ${price}`);
  }
  assert.ok(appSource.includes("No subscription"));
});

test("pilot application is local-first and requires valid acknowledged input", () => {
  assert.ok(appSource.includes("mailto:"));
  assert.ok(appSource.includes("navigator.clipboard.writeText"));
  assert.ok(appSource.includes("This preview does not send or store the form"));
  assert.ok(appSource.includes("checkValidity"));
  assert.ok(appSource.includes("reportValidity"));
  assert.ok(appSource.includes("Number(form.requestedAmount) > 0"));
  assert.ok(appSource.includes("funding is not guaranteed"));
  assert.ok(appSource.includes("official notice controls"));
  assert.ok(appSource.includes("consent"));
});

test("legal and disclosure routes are present", () => {
  assert.ok(appSource.includes('"/privacy"'));
  assert.ok(appSource.includes('"/terms"'));
  assert.ok(appSource.includes('"/disclaimer"'));
  assert.ok(appSource.includes("Not affiliated with Grants.gov or the United States government"));
  assert.ok(appSource.includes("Software-assisted drafting"));
});

test("preview is intentionally excluded from search indexing", () => {
  assert.ok(htmlSource.includes('content="noindex, nofollow, noarchive"'));
  assert.ok(vercelSource.includes("X-Robots-Tag"));
  assert.ok(robotsSource.includes("Disallow: /"));
});

test("Vercel response headers apply a restrictive browser policy", () => {
  const config = JSON.parse(vercelSource);
  const headers = config.headers[0].headers;
  const headerNames = new Set(headers.map((item) => item.key));
  for (const required of [
    "Content-Security-Policy",
    "Permissions-Policy",
    "Referrer-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
  ]) {
    assert.ok(headerNames.has(required), `missing ${required}`);
  }
});
