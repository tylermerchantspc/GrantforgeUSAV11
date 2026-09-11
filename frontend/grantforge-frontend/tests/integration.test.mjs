import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appSource = fs.readFileSync(path.resolve(__dirname, "../src/App.jsx"), "utf8");
const fetcherSource = fs.readFileSync(path.resolve(__dirname, "../src/fetcher.js"), "utf8");
const configSource = fs.readFileSync(path.resolve(__dirname, "../src/config.js"), "utf8");
const htmlSource = fs.readFileSync(path.resolve(__dirname, "../index.html"), "utf8");
const vercelSource = fs.readFileSync(path.resolve(__dirname, "../vercel.json"), "utf8");
const robotsSource = fs.readFileSync(path.resolve(__dirname, "../public/robots.txt"), "utf8");

test("public customer flow exposes intake, matching, preview, checkout, and fulfillment", () => {
  assert.ok(appSource.includes("shortlist"));
  assert.ok(appSource.includes("getPreview"));
  assert.ok(appSource.includes("createCheckoutSession"));
  assert.ok(appSource.includes("createDownloadToken"));
  assert.ok(appSource.includes("receiptByToken"));
  assert.ok(appSource.includes("downloadUrlByToken"));
  assert.ok(appSource.includes("Find my grants"));
  assert.ok(appSource.includes("Preview this draft"));
  assert.ok(appSource.includes("Purchase full draft"));
  assert.ok(appSource.includes('path === "/thanks"'));
});

test("one flat public draft price is used for every supported applicant", () => {
  assert.ok(appSource.includes('const FLAT_DRAFT_PRICE = "$49.99"'));
  assert.equal(appSource.includes("$9.99"), false);
  assert.equal(appSource.includes("$99.99"), false);
  assert.equal(appSource.includes("$199.99"), false);
  assert.ok(appSource.includes("One flat price for every supported applicant type and funding amount"));
});

test("intake requires core organization and project information plus accuracy confirmation", () => {
  for (const field of [
    "organization",
    "contactName",
    "contactEmail",
    "category",
    "annualBudget",
    "amountRequested",
    "projectTitle",
    "keywords",
    "timeline",
    "audience",
    "accuracy",
  ]) {
    assert.ok(appSource.includes(`name=\"${field}\"`) || appSource.includes(`${field}:`), `missing ${field}`);
  }
  assert.ok(appSource.includes("checkValidity"));
  assert.ok(appSource.includes("reportValidity"));
  assert.ok(appSource.includes("confirm it is accurate"));
});

test("match results expose qualification, official source, and preview before payment", () => {
  for (const label of ["HIGH", "LOW", "NO"]) {
    assert.ok(appSource.includes(`label: \"${label}\"`), `missing ${label}`);
  }
  assert.ok(appSource.includes("Preliminary qualification"));
  assert.ok(appSource.includes("View official Grants.gov opportunity"));
  assert.ok(appSource.includes("No payment to search"));
  assert.ok(appSource.includes("No payment to view your match results or quick preview"));
});

test("checkout requires final-sale and information-accuracy acknowledgement", () => {
  assert.ok(appSource.includes("I have checked my information and selected grant"));
  assert.ok(appSource.includes("customized drafting service immediately after payment"));
  assert.ok(appSource.includes("final and non-refundable once generation begins"));
  assert.ok(appSource.includes("Confirm the final-sale and information-accuracy terms before checkout"));
});

test("technology is positioned as proprietary software without public AI branding", () => {
  assert.ok(appSource.includes("proprietary software"));
  assert.equal(/\bAI\b/.test(appSource), false);
});

test("public intake includes higher education and no student-aid surface", () => {
  assert.ok(appSource.includes("College / University / Research Institution"));
  assert.ok(appSource.includes("principal investigator"));
  assert.equal(/\bFAFSA\b/i.test(appSource), false);
  assert.equal(/student aid/i.test(appSource), false);
});

test("frontend API client contains matching, preview, checkout, and delivery wiring", () => {
  for (const endpointKey of [
    "ENDPOINTS.questionnaire",
    "ENDPOINTS.preview",
    "ENDPOINTS.checkout",
    "ENDPOINTS.createDownloadToken",
    "ENDPOINTS.receipt",
    "ENDPOINTS.downloadBySession",
  ]) {
    assert.ok(fetcherSource.includes(endpointKey), `missing ${endpointKey}`);
  }
  for (const route of [
    "/questionnaire",
    "/preview",
    "/create-checkout-session",
    "/create-download-token",
    "/receipt",
    "/download-by-session",
  ]) {
    assert.ok(configSource.includes(route), `missing ${route}`);
  }
  assert.ok(fetcherSource.includes("includeExpired: false"));
});

test("legal and disclosure routes are present", () => {
  assert.ok(appSource.includes('"/privacy"'));
  assert.ok(appSource.includes('"/terms"'));
  assert.ok(appSource.includes('"/disclaimer"'));
  assert.ok(appSource.includes("Not affiliated with Grants.gov or the United States government"));
  assert.ok(appSource.toLowerCase().includes("all sales are final and non-refundable"));
  assert.ok(appSource.includes("official funding notice controls"));
});

test("Vercel demo remains excluded from search indexing until custom-domain launch", () => {
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