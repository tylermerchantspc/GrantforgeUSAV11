import { useState } from "react";
import "./App.css";

const PILOT_EMAIL = (
  import.meta.env.VITE_PILOT_EMAIL ||
  ["tylermerchantspc", "gmail.com"].join("@")
).trim();

const PRICING = [
  {
    audience: "Teachers and classroom projects",
    price: "$9.99",
    detail: "For an individual educator preparing one classroom-focused draft.",
  },
  {
    audience: "Organizations up to $500,000",
    price: "$49.99",
    detail: "Based on the applicant organization's annual operating budget.",
  },
  {
    audience: "$500,000 to $2 million",
    price: "$99.99",
    detail: "For established organizations with a larger operating footprint.",
  },
  {
    audience: "More than $2 million",
    price: "$199.99",
    detail: "For larger organizations and more complex institutional context.",
  },
];

const INITIAL_FORM = {
  organization: "",
  contactName: "",
  contactEmail: "",
  applicantType: "",
  annualBudget: "",
  requestedAmount: "",
  targetDate: "",
  projectSummary: "",
  knownOpportunity: "",
  acknowledge: false,
  consent: false,
};

const LEGAL_PAGES = {
  "/privacy": {
    eyebrow: "Founding-pilot policy",
    title: "Privacy notice",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "What this preview collects",
        "The application form is processed in your browser. GrantForgeUSA does not receive the information unless you choose to send the prepared email. This preview does not use an account system, payment form, advertising tracker, or applicant database.",
      ],
      [
        "Email applications",
        "When you send an application email, GrantForgeUSA receives the information in that message and standard email metadata. Your email provider and GrantForgeUSA's email provider also process the message under their respective terms and privacy practices.",
      ],
      [
        "How information is used",
        "Application information is used to evaluate pilot fit, communicate about the request, verify a potential federal opportunity, scope an engagement, and, after written acceptance, prepare the requested work. GrantForgeUSA does not sell pilot applicant information.",
      ],
      [
        "Sensitive information",
        "Do not submit Social Security numbers, bank or card information, passwords, protected health information, student education records, export-controlled information, or other sensitive personal data through the pilot application.",
      ],
      [
        "Retention and deletion",
        "Pilot application emails may be retained for operations, security, recordkeeping, and legal obligations. A requester may ask for deletion unless retention is required for an active engagement, dispute, accounting obligation, or applicable law.",
      ],
      [
        "Contact",
        `Privacy and deletion requests may be sent to ${PILOT_EMAIL}.`,
      ],
    ],
  },
  "/terms": {
    eyebrow: "Founding-pilot policy",
    title: "Pilot terms",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "Application status",
        "Sending a pilot application is a request for consideration only. It does not guarantee acceptance, reserve capacity, create a client relationship, or obligate either party to proceed.",
      ],
      [
        "Written acceptance controls",
        "An engagement begins only after GrantForgeUSA accepts the project in writing and confirms the opportunity, scope, price, delivery target, applicant responsibilities, and any additional terms. This preview does not collect payment.",
      ],
      [
        "Applicant information",
        "The applicant is responsible for supplying accurate, complete, authorized information. GrantForgeUSA may decline or pause work when material information is missing, inconsistent, confidential beyond agreed safeguards, or unsuitable for the pilot.",
      ],
      [
        "Draft nature of deliverables",
        "Pilot deliverables are editable drafting and research aids. They are not completed government submissions, agency determinations, legal opinions, tax advice, audits, certifications, or representations that the applicant is eligible or will receive funding.",
      ],
      [
        "Official requirements and submission",
        "The official funding notice, agency instructions, Grants.gov requirements, and applicable law control. The applicant remains responsible for registrations, factual verification, attachments, budgets, certifications, signatures, deadlines, and final submission.",
      ],
      [
        "Final engagement terms",
        "GrantForgeUSA may revise pilot capacity, pricing, or preview terms as testing proceeds. Any written engagement terms supplied at acceptance govern that engagement if they conflict with this preview page.",
      ],
    ],
  },
  "/disclaimer": {
    eyebrow: "Founding-pilot policy",
    title: "Service disclaimer",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "Independent service",
        "GrantForgeUSA, LLC is an independent private business. It is not Grants.gov, a federal agency, a state agency, or an authorized representative of the United States government.",
      ],
      [
        "No guarantee",
        "GrantForgeUSA does not guarantee that a particular opportunity is available, that an applicant is eligible, that an application is complete or compliant, that an agency will review it, or that funding will be awarded.",
      ],
      [
        "Official notice controls",
        "Federal opportunities may change, close, be amended, or be withdrawn. The current official notice and agency instructions are the controlling source. Applicants must independently confirm all material requirements before relying on a draft or submitting an application.",
      ],
      [
        "Software-assisted drafting",
        "GrantForgeUSA may use proprietary software and automated tools to support research organization, drafting, editing, and quality checks. Human review reduces risk but does not eliminate possible errors, omissions, outdated information, unsupported statements, or unsuitable language.",
      ],
      [
        "Applicant responsibility",
        "The applicant must review and approve every factual statement, budget assumption, commitment, certification, disclosure, and attachment. GrantForgeUSA does not sign, certify, or submit a federal application on the applicant's behalf during the founding pilot.",
      ],
      [
        "Professional advice",
        "The service is not legal, accounting, tax, lobbying, procurement, cybersecurity, records-management, or regulatory advice. Consult an appropriately qualified professional when those matters affect the application or organization.",
      ],
    ],
  },
};

function Brand() {
  return (
    <a className="brand" href="/" aria-label="GrantForgeUSA home">
      <span className="brand-icon" aria-hidden="true">GF</span>
      <span className="brand-copy">
        <strong>GrantForgeUSA</strong>
        <small>Federal grant drafting support</small>
      </span>
    </a>
  );
}

function Header() {
  return (
    <>
      <div className="pilot-banner">
        Founding-pilot soft launch — applications are open for a limited 3–5 organization cohort.
      </div>
      <header className="site-header">
        <div className="shell header-inner">
          <Brand />
          <nav aria-label="Primary navigation">
            <a href="/#process">Process</a>
            <a href="/#deliverables">Deliverables</a>
            <a href="/#pricing">Pricing</a>
            <a className="nav-cta" href="/#apply">Apply</a>
          </nav>
        </div>
      </header>
    </>
  );
}

function Footer() {
  return (
    <footer className="site-footer">
      <div className="shell footer-main">
        <div>
          <Brand />
          <p>
            Independent, proprietary software-assisted grant drafting support under human review.
          </p>
        </div>
        <div className="footer-links">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Pilot terms</a>
          <a href="/disclaimer">Disclaimer</a>
          <a href={`mailto:${PILOT_EMAIL}`}>Contact</a>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>© 2026 GrantForgeUSA, LLC</span>
        <span>Not affiliated with Grants.gov or the United States government.</span>
      </div>
    </footer>
  );
}

function buildApplication(form) {
  return [
    "GRANTFORGEUSA FOUNDING-PILOT APPLICATION",
    "",
    `Organization: ${form.organization}`,
    `Contact name: ${form.contactName}`,
    `Contact email: ${form.contactEmail}`,
    `Applicant type: ${form.applicantType}`,
    `Annual operating budget: ${form.annualBudget}`,
    `Approximate amount requested: $${form.requestedAmount}`,
    `Target funding or submission date: ${form.targetDate || "Not specified"}`,
    "",
    "Project summary:",
    form.projectSummary,
    "",
    "Known federal opportunity or Grants.gov link/number:",
    form.knownOpportunity || "None supplied",
    "",
    "Acknowledgments:",
    "- I understand that GrantForgeUSA does not guarantee funding and does not submit an application for me.",
    "- I understand that the current official federal notice controls.",
    "- I remain responsible for facts, registrations, certifications, attachments, signatures, deadlines, and submission.",
    "- I consent to being contacted about this pilot application.",
  ].join("\n");
}

function LandingPage() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [status, setStatus] = useState("");
  const [fallbackText, setFallbackText] = useState("");

  function updateField(event) {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : value,
    }));
    setStatus("");
    setFallbackText("");
  }

  function isComplete() {
    return Boolean(
      form.organization.trim() &&
      form.contactName.trim() &&
      form.contactEmail.trim() &&
      form.applicantType &&
      form.annualBudget &&
      form.requestedAmount &&
      form.projectSummary.trim() &&
      form.acknowledge &&
      form.consent
    );
  }

  function prepareEmail(event) {
    event.preventDefault();
    if (!isComplete()) {
      setStatus("Complete the required fields and acknowledgments before preparing the email.");
      return;
    }

    const subject = `[GrantForgeUSA Pilot] ${form.organization.trim()}`;
    const body = buildApplication(form);
    setStatus("Your application email is prepared. Review it in your email program, then send it.");
    window.location.href = `mailto:${PILOT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  async function copyApplication() {
    if (!isComplete()) {
      setStatus("Complete the required fields and acknowledgments before copying the application.");
      return;
    }

    const body = buildApplication(form);
    try {
      await navigator.clipboard.writeText(body);
      setStatus(`Application copied. Email it to ${PILOT_EMAIL} with the subject “GrantForgeUSA Pilot.”`);
    } catch {
      setFallbackText(body);
      setStatus("Automatic copy was unavailable. Select and copy the application text below.");
    }
  }

  return (
    <div className="site">
      <Header />
      <main>
        <section className="hero">
          <div className="shell hero-grid">
            <div>
              <span className="eyebrow">Controlled public preview · September 2026</span>
              <h1>Federal grant work, structured for small teams.</h1>
              <p className="hero-lead">
                GrantForgeUSA helps eligible organizations identify a current federal opportunity and develop a clear,
                editable proposal draft package. The founding pilot combines official-source research, proprietary drafting
                software, and human review before delivery.
              </p>
              <div className="button-row">
                <a className="button primary" href="#apply">Apply for the founding pilot</a>
                <a className="button secondary" href="#process">Review the process</a>
              </div>
              <p className="microcopy">
                No payment is collected on this preview. Acceptance, scope, price, and timing are confirmed in writing first.
              </p>
            </div>
            <aside className="launch-card" aria-label="Founding-pilot operating parameters">
              <span>Founding-pilot parameters</span>
              <dl>
                <div><dt>Cohort</dt><dd>3–5 selected organizations</dd></div>
                <div><dt>Opportunity source</dt><dd>Verified against an official federal notice</dd></div>
                <div><dt>Delivery target</dt><dd>Within 48 hours after acceptance, complete intake, and verification</dd></div>
                <div><dt>Submission</dt><dd>Completed by the applicant, not GrantForgeUSA</dd></div>
              </dl>
            </aside>
          </div>
        </section>

        <section className="trust-strip" aria-label="Service safeguards">
          <div className="shell trust-grid">
            <div><strong>Official-source first</strong><span>The current federal notice is the controlling source.</span></div>
            <div><strong>Human review</strong><span>Software-assisted drafting is reviewed before pilot delivery.</span></div>
            <div><strong>No funding promises</strong><span>Eligibility and award decisions remain with the agency.</span></div>
          </div>
        </section>

        <section id="process" className="section">
          <div className="shell">
            <div className="section-heading">
              <span className="eyebrow">How the pilot works</span>
              <h2>A controlled workflow before full-service launch.</h2>
              <p>
                Volume is intentionally limited so research quality, drafting controls, turnaround, and client handoff can be
                measured before paid service opens broadly.
              </p>
            </div>
            <ol className="steps">
              <li><span>01</span><h3>Apply</h3><p>Provide a concise project brief, organization type, funding need, and timing.</p></li>
              <li><span>02</span><h3>Verify</h3><p>A current notice is checked for status, deadline, eligibility, award range, and core requirements.</p></li>
              <li><span>03</span><h3>Draft</h3><p>GrantForgeUSA develops a software-assisted, human-reviewed narrative and working compliance package.</p></li>
              <li><span>04</span><h3>Review and submit</h3><p>You verify facts, complete attachments and registrations, certify, and submit.</p></li>
            </ol>
          </div>
        </section>

        <section id="deliverables" className="section contrast">
          <div className="shell two-panel">
            <div className="section-heading left">
              <span className="eyebrow">Pilot draft package</span>
              <h2>Less blank-page time. Clear applicant responsibility.</h2>
              <p>
                Each engagement is scoped against one verified opportunity. Deliverables depend on the notice and the quality
                of the applicant information supplied.
              </p>
            </div>
            <div className="check-card">
              <ul>
                <li>Official opportunity link and basic fit summary</li>
                <li>Editable core narrative organized around the notice</li>
                <li>Working objectives, activities, outcomes, and evaluation language</li>
                <li>Budget-use narrative framework when supported by intake</li>
                <li>Requirements and missing-information checklist</li>
                <li>Items requiring applicant confirmation before submission</li>
              </ul>
              <p>
                The package is a drafting aid, not a completed government filing, legal opinion, certification, or guarantee of eligibility.
              </p>
            </div>
          </div>
        </section>

        <section id="pricing" className="section">
          <div className="shell">
            <div className="section-heading">
              <span className="eyebrow">Planned introductory pricing</span>
              <h2>One standard draft package. No subscription.</h2>
              <p>
                These are the intended pilot prices for accepted standard-scope engagements. The applicable tier and exact
                scope are confirmed in writing before payment is requested.
              </p>
            </div>
            <div className="pricing-grid">
              {PRICING.map((tier) => (
                <article className="price-card" key={tier.price}>
                  <span>{tier.audience}</span>
                  <strong>{tier.price}</strong>
                  <p>{tier.detail}</p>
                </article>
              ))}
            </div>
            <p className="pricing-note">
              Multiple opportunities, extensive attachments, unusual compliance requirements, or materially incomplete intake may require a separate scope.
            </p>
          </div>
        </section>

        <section id="apply" className="section apply-section">
          <div className="shell apply-grid">
            <div className="section-heading left apply-copy">
              <span className="eyebrow">Founding-pilot application</span>
              <h2>Request a place in the first public cohort.</h2>
              <p>
                Applying does not create a contract, guarantee acceptance, or authorize a charge. Do not include Social Security
                numbers, bank information, passwords, protected health information, student records, or other sensitive data.
              </p>
              <div className="fit-note">
                <strong>Best fit</strong>
                <p>Organizations with a defined project, a realistic funding need, and enough internal information to verify facts and complete required attachments.</p>
              </div>
            </div>

            <form className="application-form" onSubmit={prepareEmail}>
              <div className="form-grid">
                <label>Organization name <em>*</em><input name="organization" value={form.organization} onChange={updateField} autoComplete="organization" required /></label>
                <label>Contact name <em>*</em><input name="contactName" value={form.contactName} onChange={updateField} autoComplete="name" required /></label>
              </div>
              <label>Contact email <em>*</em><input type="email" name="contactEmail" value={form.contactEmail} onChange={updateField} autoComplete="email" required /></label>
              <div className="form-grid">
                <label>
                  Applicant type <em>*</em>
                  <select name="applicantType" value={form.applicantType} onChange={updateField} required>
                    <option value="">Select one</option>
                    <option>Teacher or classroom</option>
                    <option>School or school district</option>
                    <option>Church or faith organization</option>
                    <option>501(c)(3) nonprofit</option>
                    <option>Small business</option>
                    <option>City, county, or municipality</option>
                    <option>Other organization</option>
                  </select>
                </label>
                <label>
                  Annual operating budget <em>*</em>
                  <select name="annualBudget" value={form.annualBudget} onChange={updateField} required>
                    <option value="">Select one</option>
                    <option>Teacher or classroom — not applicable</option>
                    <option>Up to $500,000</option>
                    <option>$500,000 to $2 million</option>
                    <option>More than $2 million</option>
                    <option>Not yet known</option>
                  </select>
                </label>
              </div>
              <div className="form-grid">
                <label>Approximate amount requested <em>*</em><input type="number" name="requestedAmount" value={form.requestedAmount} onChange={updateField} min="1" step="1" required /></label>
                <label>Target funding or submission date<input type="date" name="targetDate" value={form.targetDate} onChange={updateField} /></label>
              </div>
              <label>
                Project summary <em>*</em>
                <textarea name="projectSummary" value={form.projectSummary} onChange={updateField} rows="7" maxLength="1800" placeholder="Describe the problem, people served, planned activities, location, timeline, and intended result." required />
                <small>{form.projectSummary.length}/1800 characters</small>
              </label>
              <label>Known federal opportunity number or Grants.gov link<input name="knownOpportunity" value={form.knownOpportunity} onChange={updateField} placeholder="Optional" /></label>

              <fieldset>
                <legend>Required acknowledgments</legend>
                <label className="check-label">
                  <input type="checkbox" name="acknowledge" checked={form.acknowledge} onChange={updateField} required />
                  <span>I understand that funding is not guaranteed, the official notice controls, and I remain responsible for final verification, registrations, certifications, attachments, signatures, deadlines, and submission.</span>
                </label>
                <label className="check-label">
                  <input type="checkbox" name="consent" checked={form.consent} onChange={updateField} required />
                  <span>I consent to GrantForgeUSA contacting me about this pilot application.</span>
                </label>
              </fieldset>

              <div className="button-row form-buttons">
                <button className="button primary" type="submit">Prepare application email</button>
                <button className="button secondary" type="button" onClick={copyApplication}>Copy application instead</button>
              </div>
              <p className="form-note">
                This preview does not send or store the form. The first button opens your email program; you decide whether to send it. Review the <a href="/privacy">privacy notice</a> first.
              </p>
              <p className="form-status" role="status" aria-live="polite">{status}</p>
              {fallbackText && (
                <label className="copy-box">Application text<textarea readOnly rows="16" value={fallbackText} onFocus={(event) => event.target.select()} /></label>
              )}
            </form>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}

function LegalPage({ page }) {
  return (
    <div className="site legal-site">
      <Header />
      <main className="legal-main">
        <div className="shell legal-shell">
          <a className="back-link" href="/">← Back to the pilot site</a>
          <span className="eyebrow">{page.eyebrow}</span>
          <h1>{page.title}</h1>
          <p className="effective">{page.effective}</p>
          <div className="legal-card">
            {page.sections.map(([heading, body]) => (
              <section key={heading}>
                <h2>{heading}</h2>
                <p>{body}</p>
              </section>
            ))}
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function CheckoutPaused() {
  return (
    <div className="site legal-site">
      <Header />
      <main className="legal-main">
        <div className="shell legal-shell">
          <span className="eyebrow">Soft-launch status</span>
          <h1>Online checkout is paused.</h1>
          <div className="legal-card single-card">
            <p>
              The founding-pilot preview does not process payments or create downloadable orders. A project must be reviewed and accepted in writing before any payment is requested.
            </p>
            <a className="button primary" href="/">Return to the pilot site</a>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  const path = typeof window === "undefined" ? "/" : window.location.pathname.replace(/\/$/, "") || "/";
  if (LEGAL_PAGES[path]) return <LegalPage page={LEGAL_PAGES[path]} />;
  if (path === "/thanks") return <CheckoutPaused />;
  return <LandingPage />;
}
