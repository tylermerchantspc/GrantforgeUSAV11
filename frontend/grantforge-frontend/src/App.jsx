import { useEffect, useMemo, useState } from "react";
import {
  createCheckoutSession,
  createDownloadToken,
  downloadUrlByToken,
  getPreview,
  receiptByToken,
  shortlist,
} from "./fetcher";
import "./App.css";
import "./flow.css";

const SUPPORT_EMAIL = (
  import.meta.env.VITE_SUPPORT_EMAIL ||
  import.meta.env.VITE_PILOT_EMAIL ||
  ["tylermerchantspc", "gmail.com"].join("@")
).trim();

const FLAT_DRAFT_PRICE = "$49.99";

function serviceFeeFor() {
  return FLAT_DRAFT_PRICE;
}

const INITIAL_FORM = {
  organization: "",
  contactName: "",
  contactEmail: "",
  zip: "",
  state: "",
  category: "",
  annualBudget: "",
  amountRequested: "",
  projectTitle: "",
  keywords: "",
  timeline: "",
  audience: "",
  need: "",
  notes: "",
  accuracy: false,
};

const LEGAL_PAGES = {
  "/privacy": {
    eyebrow: "Privacy",
    title: "Privacy notice",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "Information you provide",
        "GrantForgeUSA processes the information you enter into the intake and purchase flow to search for potential funding opportunities, estimate preliminary fit, prepare previews, create a selected proposal draft, support payment and delivery, prevent abuse, and provide customer support.",
      ],
      [
        "Payment information",
        "Payment card information is collected and processed by the payment provider used at checkout. GrantForgeUSA does not ask you to place card numbers, bank credentials, passwords, Social Security numbers, or protected health information in the project intake.",
      ],
      [
        "How information is used",
        "Information is used to operate the requested service, match the intake against potential federal opportunities, prepare drafting materials, maintain transaction records, troubleshoot service issues, and protect the service from fraud or misuse. GrantForgeUSA does not sell applicant information.",
      ],
      [
        "Proprietary software",
        "GrantForgeUSA uses proprietary software and automated processing to organize intake information, evaluate potential matches, prepare previews, and produce drafting materials. Customers remain responsible for reviewing all output and confirming the official funding notice before submission.",
      ],
      [
        "Retention",
        "Operational and transaction records may be retained as needed for security, accounting, dispute handling, legal obligations, and service improvement. Temporary technical records may be removed or replaced as systems are updated.",
      ],
      ["Contact", `Privacy questions may be sent to ${SUPPORT_EMAIL}.`],
    ],
  },
  "/terms": {
    eyebrow: "Terms of service",
    title: "GrantForgeUSA service terms",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "Service",
        "GrantForgeUSA provides proprietary software-assisted federal opportunity matching, preliminary fit information, proposal previews, and paid proposal drafting materials. The service is independent and is not Grants.gov, a federal agency, or an authorized representative of the United States government.",
      ],
      [
        "Your information must be correct",
        "You are responsible for entering accurate, complete, and authorized information about your organization, project, requested funding, eligibility, budget, target population, and other material facts. Review the intake and selected opportunity before purchasing. Draft quality and match quality depend on the information supplied.",
      ],
      [
        "Preliminary match information",
        "High, Low, No, Strong Match, Possible Match, scores, previews, and similar indicators are GrantForgeUSA screening estimates. They are not agency eligibility determinations, approvals, certifications, legal opinions, or promises that an application will be accepted or funded. The current official funding notice controls.",
      ],
      [
        "Purchases and refunds",
        "Payment purchases an immediately performed customized digital drafting service for the selected opportunity and authorizes GrantForgeUSA to begin generation using the submitted intake. Because the work is prepared specifically for the customer, all sales are final and non-refundable once generation begins except where required by applicable law or when GrantForgeUSA fails to deliver the purchased service. Funding denial, agency changes, customer ineligibility, or inaccurate customer-supplied information do not create a refund entitlement. GrantForgeUSA may correct or re-perform a technically defective delivery when appropriate.",
      ],
      [
        "Customer review and submission",
        "The customer must review and edit the draft, verify every factual statement and budget assumption, complete registrations and attachments, make required certifications and signatures, and submit the final application. GrantForgeUSA does not guarantee eligibility, compliance, review, scoring, or funding.",
      ],
      [
        "Official requirements",
        "Federal notices, agency instructions, Grants.gov requirements, amendments, deadlines, laws, and regulations control over any GrantForgeUSA summary or draft. Opportunities may change, close, be amended, or be withdrawn after matching.",
      ],
    ],
  },
  "/disclaimer": {
    eyebrow: "Important notice",
    title: "Service disclaimer",
    effective: "Effective September 10, 2026",
    sections: [
      [
        "Independent private service",
        "GrantForgeUSA, LLC is an independent private business. It is not affiliated with or endorsed by Grants.gov or the United States government.",
      ],
      [
        "No award guarantee",
        "GrantForgeUSA does not guarantee that an opportunity remains open, that an applicant is eligible, that a draft satisfies every requirement, that an agency will review an application, or that funding will be awarded.",
      ],
      [
        "Qualification indicators",
        "The High, Low, and No qualification scale is a preliminary GrantForgeUSA fit estimate derived from the information supplied and the opportunity data available to the service. It should be used as a screening aid, not as an official agency determination.",
      ],
      [
        "Drafting output",
        "Proposal drafts are editable working materials produced with GrantForgeUSA proprietary software. They may contain errors, omissions, unsupported assumptions, or language that requires revision. Review the complete official notice and validate the draft before use.",
      ],
      [
        "Professional advice",
        "GrantForgeUSA does not provide legal, tax, accounting, lobbying, procurement, cybersecurity, records-management, or regulatory advice. Obtain qualified professional advice where those issues affect your application.",
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
        <small>Federal grant matching &amp; drafting</small>
      </span>
    </a>
  );
}

function Header() {
  return (
    <>
      <div className="service-banner">
        Free grant matching and preview · One full proposal draft: $49.99
      </div>
      <header className="site-header">
        <div className="shell header-inner">
          <Brand />
          <nav aria-label="Primary navigation">
            <a href="/#process">How it works</a>
            <a href="/#pricing">Pricing</a>
            <a href="/#start">Find grants</a>
            <a className="nav-cta" href="/#start">Start free</a>
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
            Proprietary software for federal grant opportunity matching, proposal previews, and editable draft preparation.
          </p>
        </div>
        <div className="footer-links">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <a href="/disclaimer">Disclaimer</a>
          <a href={`mailto:${SUPPORT_EMAIL}`}>Contact</a>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>© 2026 GrantForgeUSA, LLC</span>
        <span>Independent service · Not affiliated with Grants.gov or the United States government.</span>
      </div>
    </footer>
  );
}

function LegalPage({ page }) {
  return (
    <div className="site">
      <Header />
      <main className="legal-main">
        <div className="shell legal-shell">
          <span className="eyebrow">{page.eyebrow}</span>
          <h1>{page.title}</h1>
          <p className="legal-effective">{page.effective}</p>
          <div className="legal-card">
            {page.sections.map(([heading, body]) => (
              <section key={heading}>
                <h2>{heading}</h2>
                <p>{body}</p>
              </section>
            ))}
          </div>
          <a className="button secondary" href="/">Return to GrantForgeUSA</a>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function qualificationFor(grant) {
  const fit = String(grant?.fit || "").toLowerCase();
  if (fit.includes("strong")) return { label: "HIGH", level: 3, className: "high" };
  if (fit.includes("possible")) return { label: "LOW", level: 2, className: "low" };
  return { label: "NO", level: 1, className: "no" };
}

function QualificationScale({ grant }) {
  const q = qualificationFor(grant);
  return (
    <div className="qualification" aria-label={`Preliminary qualification ${q.label}`}>
      <div className="qualification-head">
        <span>Preliminary qualification</span>
        <strong className={`qualification-label ${q.className}`}>{q.label}</strong>
      </div>
      <div className="qualification-scale" aria-hidden="true">
        <span className={q.level >= 1 ? "active no" : ""}>No</span>
        <span className={q.level >= 2 ? "active low" : ""}>Low</span>
        <span className={q.level >= 3 ? "active high" : ""}>High</span>
      </div>
      <small>Screening estimate only. The official funding notice controls eligibility.</small>
    </div>
  );
}

function formatMoney(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return "Not listed";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(num);
}

function compactPreview(text) {
  if (!text) return "";
  const blocks = String(text)
    .split(/\n\n+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 2);
  const joined = blocks.join("\n\n");
  return joined.length > 1500 ? `${joined.slice(0, 1500).trim()}…` : joined;
}

function GrantCard({ grant, selected, onSelect, onPreview }) {
  const q = qualificationFor(grant);
  const canPurchase = Boolean(grant.purchasable) && q.label !== "NO";
  return (
    <article className={`grant-card ${selected ? "selected" : ""}`}>
      <div className="grant-card-top">
        <span className={`fit-pill ${q.className}`}>{q.label} fit</span>
        {grant.score !== undefined && <span className="score-pill">Match score {grant.score}</span>}
      </div>
      <h3>{grant.title || "Federal funding opportunity"}</h3>
      <p className="grant-summary">
        {grant.summary || "Review the official notice and GrantForgeUSA preview for program details."}
      </p>
      {grant.fit_notes && <p className="fit-explanation"><strong>Why this match:</strong> {grant.fit_notes}</p>}
      <dl className="grant-meta">
        <div><dt>Maximum award</dt><dd>{formatMoney(grant.max_amount)}</dd></div>
        <div><dt>Deadline</dt><dd>{grant.deadline || "TBA"}</dd></div>
        <div><dt>Level</dt><dd>{grant.level || "Federal"}</dd></div>
        <div><dt>Source</dt><dd>{String(grant.source || "").includes("Grants.gov") ? "Live Grants.gov" : "Verified federal data"}</dd></div>
      </dl>
      <QualificationScale grant={grant} />
      <div className="grant-actions">
        <button className="button primary" type="button" onClick={() => onPreview(grant)} disabled={!canPurchase}>
          {canPurchase ? "Preview this draft" : "Not purchase-ready"}
        </button>
        <button className="button secondary" type="button" onClick={() => onSelect(grant)} disabled={!canPurchase}>
          {selected ? "Selected" : "Select grant"}
        </button>
      </div>
      {grant.program_url && (
        <a className="official-link" href={grant.program_url} target="_blank" rel="noreferrer">
          View official Grants.gov opportunity ↗
        </a>
      )}
    </article>
  );
}

function ThankYouPage() {
  const checkoutRef = useMemo(() => new URLSearchParams(window.location.search).get("ref") || "", []);
  const [phase, setPhase] = useState("checking");
  const [token, setToken] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function finalize() {
      if (!checkoutRef) {
        setError("This return link is missing its checkout reference.");
        setPhase("error");
        return;
      }

      const tokenResponse = await createDownloadToken(checkoutRef);
      if (cancelled) return;
      if (!tokenResponse?.ok || !tokenResponse?.token) {
        setError(tokenResponse?.error || "Payment could not be confirmed automatically.");
        setPhase("error");
        return;
      }

      const newToken = tokenResponse.token;
      const receiptResponse = await receiptByToken(newToken);
      if (cancelled) return;
      if (!receiptResponse?.ok) {
        setError(receiptResponse?.error || "Your receipt could not be loaded.");
        setPhase("error");
        return;
      }

      setToken(newToken);
      setReceipt(receiptResponse);
      setPhase("ready");
      sessionStorage.removeItem("grantforge_checkout_context");
    }

    finalize();
    return () => {
      cancelled = true;
    };
  }, [checkoutRef]);

  return (
    <div className="site">
      <Header />
      <main className="thanks-main">
        <div className="shell thanks-shell">
          {phase === "checking" && (
            <div className="thanks-card">
              <span className="eyebrow">Payment return</span>
              <h1>Confirming your order.</h1>
              <p>GrantForgeUSA is verifying payment and preparing the secure draft download.</p>
              <div className="loading-line" aria-label="Loading" />
            </div>
          )}

          {phase === "ready" && (
            <div className="thanks-card success-card">
              <span className="eyebrow">Order confirmed</span>
              <h1>Your full proposal draft is ready.</h1>
              <p>
                Payment has been confirmed. Download and save the PDF now, then review every section against the current official funding notice before submission.
              </p>
              <dl className="receipt-grid">
                <div><dt>Order</dt><dd>{receipt?.order_id || "Confirmed"}</dd></div>
                <div><dt>Amount</dt><dd>{receipt?.amount_total ? formatMoney(receipt.amount_total) : "Paid"}</dd></div>
              </dl>
              <a className="button primary download-button" href={downloadUrlByToken(token)}>
                Download full draft PDF
              </a>
              <p className="download-warning">
                Save the file when it opens. The secure download token is limited and the service may block repeated downloads for the same order.
              </p>
              <a className="button secondary" href="/">Start another grant search</a>
            </div>
          )}

          {phase === "error" && (
            <div className="thanks-card error-card">
              <span className="eyebrow">Order assistance</span>
              <h1>We could not complete the automatic handoff.</h1>
              <p>{error}</p>
              <p>
                If you completed payment, do not purchase again. Contact <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a> with your checkout receipt so the order can be verified.
              </p>
              <a className="button secondary" href="/">Return to GrantForgeUSA</a>
            </div>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}

function LandingPage() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [notice, setNotice] = useState("");
  const [results, setResults] = useState([]);
  const [selectedGrant, setSelectedGrant] = useState(null);
  const [previewGrant, setPreviewGrant] = useState(null);
  const [previewText, setPreviewText] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [saleTerms, setSaleTerms] = useState(false);
  const [checkoutError, setCheckoutError] = useState("");
  const [checkingOut, setCheckingOut] = useState(false);
  const serviceFee = serviceFeeFor();

  function updateField(event) {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
    setSearchError("");
  }

  function buildApiPayload(source = form) {
    return {
      organization: source.organization.trim(),
      contactName: source.contactName.trim(),
      contactEmail: source.contactEmail.trim(),
      zip: source.zip.trim(),
      state: source.state.trim(),
      category: source.category,
      annualBudget: Number(source.annualBudget),
      amountRequested: Number(source.amountRequested),
      projectTitle: source.projectTitle.trim(),
      keywords: source.keywords.trim(),
      timeline: source.timeline.trim(),
      audience: source.audience.trim(),
      need: source.need.trim(),
      notes: source.notes.trim(),
    };
  }

  async function loadPreview(grant, payload = buildApiPayload()) {
    setSelectedGrant(grant);
    setPreviewGrant(grant);
    setPreviewing(true);
    setPreviewText("");
    setPreviewError("");
    setCheckoutError("");
    setSaleTerms(false);

    const response = await getPreview({ ...payload, grant });
    if (response?.ok && response?.summary) {
      setPreviewText(compactPreview(response.summary));
    } else {
      setPreviewError(response?.error || "A preview could not be generated for this opportunity.");
    }
    setPreviewing(false);
  }

  async function searchGrants(event) {
    event.preventDefault();
    setSearchError("");
    setNotice("");
    setResults([]);
    setSelectedGrant(null);
    setPreviewGrant(null);
    setPreviewText("");
    setPreviewError("");
    setSaleTerms(false);
    setCheckoutError("");

    const formElement = event.currentTarget;
    if (!formElement.checkValidity()) {
      formElement.reportValidity();
      setSearchError("Complete the required fields before searching.");
      return;
    }
    if (!form.accuracy) {
      setSearchError("Confirm that the intake information is accurate before searching.");
      return;
    }

    setSearching(true);
    const payload = buildApiPayload();
    const response = await shortlist(payload);
    setSearching(false);

    if (!response?.ok) {
      setSearchError(response?.error || "Grant matching is temporarily unavailable.");
      return;
    }

    const matches = Array.isArray(response.results) ? response.results : [];
    setResults(matches);
    setNotice(response.notice || "");

    if (matches.length) {
      document.getElementById("matches")?.scrollIntoView({ behavior: "smooth", block: "start" });
      const firstPurchaseReady = matches.find((grant) => grant.purchasable);
      if (firstPurchaseReady) await loadPreview(firstPurchaseReady, payload);
    } else if (!response.notice) {
      setNotice("No purchase-ready federal opportunity matched this intake. Try refining the project description, keywords, applicant type, state, or funding request.");
    }
  }

  function selectGrant(grant) {
    setSelectedGrant(grant);
    setPreviewGrant(grant);
    setPreviewText("");
    setPreviewError("");
    setSaleTerms(false);
    setCheckoutError("");
  }

  async function beginCheckout() {
    if (!selectedGrant || !selectedGrant.purchasable || qualificationFor(selectedGrant).label === "NO") {
      setCheckoutError("Select a purchase-ready opportunity before continuing to checkout.");
      return;
    }
    if (!saleTerms) {
      setCheckoutError("Confirm the final-sale and information-accuracy terms before checkout.");
      return;
    }

    setCheckingOut(true);
    setCheckoutError("");
    const recommendations = results.map((grant) => ({
      title: grant.title,
      program_url: grant.program_url || grant.official_url || "",
    }));
    const payload = {
      ...buildApiPayload(),
      grant: selectedGrant,
      recommendations,
    };

    sessionStorage.setItem(
      "grantforge_checkout_context",
      JSON.stringify({ organization: form.organization, grant: selectedGrant.title, createdAt: Date.now() })
    );

    const response = await createCheckoutSession(payload);
    if (response?.ok && response?.url) {
      window.location.assign(response.url);
      return;
    }

    setCheckingOut(false);
    setCheckoutError(response?.error || "Checkout could not be started. Review the intake and selected grant, then try again.");
  }

  return (
    <div className="site">
      <Header />
      <main>
        <section className="hero public-hero">
          <div className="shell hero-grid">
            <div>
              <span className="eyebrow">Federal grant matching + proposal drafting</span>
              <h1>Find the grant. See your fit. Preview the work.</h1>
              <p className="hero-lead">
                Tell GrantForgeUSA about the eligible applicant and project. Our proprietary software screens federal opportunities, ranks the strongest matches, shows a preliminary qualification level, and gives you a proposal preview before you decide to purchase the full draft.
              </p>
              <div className="button-row">
                <a className="button primary" href="#start">Find grants free</a>
                <a className="button secondary" href="#process">See how it works</a>
              </div>
              <p className="microcopy">No payment to search. No payment to view your match results or quick preview.</p>
            </div>
            <aside className="launch-card" aria-label="GrantForgeUSA customer flow">
              <span>One streamlined workflow</span>
              <dl>
                <div><dt>1 · Intake</dt><dd>Enter your organization and project information.</dd></div>
                <div><dt>2 · Match</dt><dd>Review ranked federal opportunities and High / Low / No fit.</dd></div>
                <div><dt>3 · Preview</dt><dd>Read a short proposal sample for the grant you choose.</dd></div>
                <div><dt>4 · Draft</dt><dd>Pay only when you want the full editable proposal draft.</dd></div>
              </dl>
            </aside>
          </div>
        </section>

        <section className="trust-strip" aria-label="Service safeguards">
          <div className="shell trust-grid">
            <div><strong>Official federal links</strong><span>Matches include a direct Grants.gov reference for independent verification.</span></div>
            <div><strong>Qualification at a glance</strong><span>High, Low, or No gives you a fast preliminary fit signal.</span></div>
            <div><strong>Your choice before payment</strong><span>Search, compare, and preview first. Purchase only the grant draft you select.</span></div>
          </div>
        </section>

        <section id="process" className="section">
          <div className="shell">
            <div className="section-heading">
              <span className="eyebrow">How GrantForgeUSA works</span>
              <h2>From project idea to a working federal proposal draft.</h2>
              <p>The system keeps the expensive decision until the end: first tell us what you need, then see what actually matches.</p>
            </div>
            <ol className="steps">
              <li><span>01</span><h3>Tell us about the project</h3><p>Complete the intake with your organization, budget, funding request, audience, timeline, and project priorities.</p></li>
              <li><span>02</span><h3>See matched grants</h3><p>GrantForgeUSA screens available federal opportunities and ranks up to three candidates with fit notes and official links.</p></li>
              <li><span>03</span><h3>Choose and preview</h3><p>Select the opportunity that makes sense and read a small proposal preview before committing to the full draft.</p></li>
              <li><span>04</span><h3>Purchase your draft</h3><p>Confirm your information, pay securely, and receive the full proposal draft PDF for review and final submission work.</p></li>
            </ol>
          </div>
        </section>

        <section id="pricing" className="section contrast">
          <div className="shell pricing-public-grid">
            <div className="section-heading left">
              <span className="eyebrow">Simple decision point</span>
              <h2>Search first. Pay after you choose.</h2>
              <p>
                Grant matching, qualification indicators, official opportunity links, and the quick proposal preview are available before checkout.
              </p>
            </div>
            <div className="public-price-card">
              <span>Federal opportunity search + preview</span>
              <strong>Free</strong>
              <p>Complete the intake and compare your returned matches.</p>
              <hr />
              <span>One selected full proposal draft</span>
              <strong>{FLAT_DRAFT_PRICE}</strong>
              <p>One flat price for every supported applicant type and funding amount. Search, matching, official opportunity links, and the quick preview remain free. Customized drafting begins immediately after payment; final-sale terms apply.</p>
            </div>
          </div>
        </section>

        <section id="start" className="section apply-section intake-section">
          <div className="shell intake-layout">
            <div className="apply-copy">
              <span className="eyebrow">Start your free search</span>
              <h2>Tell us what you are trying to fund.</h2>
              <p>
                Better information creates better matching and better draft language. Use plain English and be specific about who you serve, what you want to do, and how much funding you need.
              </p>
              <div className="fit-note">
                <strong>Before you submit</strong>
                <p>Check names, budgets, funding amount, project details, and applicant type. GrantForgeUSA uses what you enter to screen opportunities and prepare the selected draft.</p>
              </div>
            </div>

            <form className="application-form intake-form" onSubmit={searchGrants}>
              <div className="form-stage"><span>1</span><strong>Organization</strong></div>
              <div className="form-grid">
                <label>
                  Applicant / organization name <em>*</em>
                  <input name="organization" value={form.organization} onChange={updateField} required autoComplete="organization" />
                </label>
                <label>
                  Applicant type <em>*</em>
                  <select name="category" value={form.category} onChange={updateField} required>
                    <option value="">Select type</option>
                    <option>K-12 School / District / Educator</option>
                    <option>Public College / University</option>
                    <option>Private College / University</option>
                    <option>Research Institution / University Research Foundation</option>
                    <option>Church / Faith Organization</option>
                    <option>501(c)(3) Nonprofit</option>
                    <option>Nonprofit / Community Organization</option>
                    <option>Small Business</option>
                    <option>For-Profit Organization</option>
                    <option>City / County / Local Government</option>
                    <option>State Government / Agency</option>
                    <option>Tribal Government / Organization</option>
                    <option>Public Housing Authority</option>
                    <option>Individual / Independent Applicant</option>
                    <option>Other Eligible Applicant</option>
                  </select>
                  {form.category === "K-12 School / District / Educator" && (
                    <small className="field-guidance">Use the school or district that would be the legal applicant. A teacher or educator may be the contact when authorized by the applicant organization.</small>
                  )}
                  {["Public College / University", "Private College / University", "Research Institution / University Research Foundation"].includes(form.category) && (
                    <small className="field-guidance">Use the legal institution as the applicant and the professor, principal investigator, dean, or grant administrator as the contact. Choose the applicant type that matches the entity that will actually submit the application.</small>
                  )}
                </label>
                <label>
                  Contact name <em>*</em>
                  <input name="contactName" value={form.contactName} onChange={updateField} required autoComplete="name" />
                </label>
                <label>
                  Contact email <em>*</em>
                  <input type="email" name="contactEmail" value={form.contactEmail} onChange={updateField} required autoComplete="email" />
                </label>
                <label>
                  State <em>*</em>
                  <select name="state" value={form.state} onChange={updateField} required autoComplete="address-level1">
                    <option value="">Select state</option>
                    {[["AL","Alabama"],["AK","Alaska"],["AZ","Arizona"],["AR","Arkansas"],["CA","California"],["CO","Colorado"],["CT","Connecticut"],["DE","Delaware"],["FL","Florida"],["GA","Georgia"],["HI","Hawaii"],["ID","Idaho"],["IL","Illinois"],["IN","Indiana"],["IA","Iowa"],["KS","Kansas"],["KY","Kentucky"],["LA","Louisiana"],["ME","Maine"],["MD","Maryland"],["MA","Massachusetts"],["MI","Michigan"],["MN","Minnesota"],["MS","Mississippi"],["MO","Missouri"],["MT","Montana"],["NE","Nebraska"],["NV","Nevada"],["NH","New Hampshire"],["NJ","New Jersey"],["NM","New Mexico"],["NY","New York"],["NC","North Carolina"],["ND","North Dakota"],["OH","Ohio"],["OK","Oklahoma"],["OR","Oregon"],["PA","Pennsylvania"],["RI","Rhode Island"],["SC","South Carolina"],["SD","South Dakota"],["TN","Tennessee"],["TX","Texas"],["UT","Utah"],["VT","Vermont"],["VA","Virginia"],["WA","Washington"],["WV","West Virginia"],["WI","Wisconsin"],["WY","Wyoming"],["DC","District of Columbia"]].map(([code, name]) => <option key={code} value={code}>{name}</option>)}
                  </select>
                </label>
                <label>
                  ZIP code
                  <input name="zip" value={form.zip} onChange={updateField} inputMode="numeric" maxLength="10" autoComplete="postal-code" />
                </label>
                <label>
                  Annual operating budget <em>*</em>
                  <input type="number" min="1" step="1" name="annualBudget" value={form.annualBudget} onChange={updateField} required inputMode="numeric" />
                </label>
              </div>

              <div className="form-stage"><span>2</span><strong>Project</strong></div>
              <div className="form-grid">
                <label>
                  Project title <em>*</em>
                  <input name="projectTitle" value={form.projectTitle} onChange={updateField} required maxLength="120" />
                </label>
                <label>
                  Funding amount requested <em>*</em>
                  <input type="number" min="1" step="1" name="amountRequested" value={form.amountRequested} onChange={updateField} required inputMode="numeric" />
                </label>
                <label>
                  Project timeline <em>*</em>
                  <input name="timeline" value={form.timeline} onChange={updateField} required placeholder="Example: 12 months" maxLength="100" />
                </label>
                <label>
                  Who will this project serve? <em>*</em>
                  <input name="audience" value={form.audience} onChange={updateField} required placeholder="Example: rural high-school students" maxLength="180" />
                </label>
              </div>

              <label>
                Search keywords / priorities <em>*</em>
                <input name="keywords" value={form.keywords} onChange={updateField} required placeholder="Example: workforce, apprenticeships, rural youth, equipment" maxLength="300" />
                <small>Use commas between major topics.</small>
              </label>

              <div className="form-stage"><span>3</span><strong>Advanced details</strong></div>
              <label>
                What problem or need are you addressing?
                <textarea name="need" value={form.need} onChange={updateField} maxLength="500" placeholder="Describe the local need, gap, or problem this project is intended to solve." />
              </label>
              <label>
                Additional project information
                <textarea name="notes" value={form.notes} onChange={updateField} maxLength="500" placeholder="Partners, existing programs, equipment needs, measurable goals, or other facts that may improve matching and drafting." />
              </label>

              <fieldset>
                <legend>Accuracy confirmation</legend>
                <label className="check-label">
                  <input type="checkbox" name="accuracy" checked={form.accuracy} onChange={updateField} required />
                  <span>I have reviewed the organization name, applicant type, state, budget, funding amount, and project information above and confirm it is accurate to the best of my knowledge. I understand match levels are preliminary screening estimates and the official funding notice controls.</span>
                </label>
              </fieldset>

              {searchError && <div className="status-message error" role="alert">{searchError}</div>}
              <div className="button-row form-buttons">
                <button className="button primary search-button" type="submit" disabled={searching}>
                  {searching ? "Searching federal opportunities…" : "Find my grants"}
                </button>
              </div>
              <p className="form-fine-print">Free search. No payment information is requested at this step.</p>
            </form>
          </div>
        </section>

        {(results.length > 0 || notice) && (
          <section id="matches" className="section results-section">
            <div className="shell">
              <div className="section-heading">
                <span className="eyebrow">Your grant matches</span>
                <h2>Review the opportunities before you buy anything.</h2>
                <p>Compare the preliminary qualification level, fit notes, award ceiling, deadline, and official notice.</p>
              </div>
              {notice && <div className="results-notice">{notice}</div>}

              {results.length > 0 && (
                <div className="results-workspace">
                  <div className="grant-list">
                    {results.map((grant, index) => (
                      <GrantCard
                        key={`${grant.opp_id || grant.opp_number || grant.title}-${index}`}
                        grant={grant}
                        selected={selectedGrant === grant}
                        onSelect={selectGrant}
                        onPreview={loadPreview}
                      />
                    ))}
                  </div>

                  <aside className="preview-checkout-card">
                    <span className="eyebrow">Quick proposal preview</span>
                    {previewGrant ? (
                      <>
                        <h3>{previewGrant.title}</h3>
                        <QualificationScale grant={previewGrant} />
                        {previewing && <div className="preview-loading"><div className="loading-line" /><p>Preparing a short preview from your intake…</p></div>}
                        {previewError && <div className="status-message error">{previewError}</div>}
                        {previewText && (
                          <div className="preview-copy">
                            {previewText.split(/\n\n+/).map((block, index) => (
                              <p key={index}>{block}</p>
                            ))}
                            <div className="preview-fade">Full proposal continues after purchase.</div>
                          </div>
                        )}
                        {!previewing && !previewText && !previewError && (
                          <button className="button secondary full-width" type="button" onClick={() => loadPreview(previewGrant)}>
                            Generate preview
                          </button>
                        )}

                        <div className="checkout-summary">
                          <div><span>Selected draft</span><strong>{serviceFee}</strong></div>
                          <p>Payment starts the customized full-draft service immediately for the opportunity selected above.</p>
                        </div>

                        <label className="check-label purchase-check">
                          <input type="checkbox" checked={saleTerms} onChange={(event) => { setSaleTerms(event.target.checked); setCheckoutError(""); }} />
                          <span>
                            I have checked my information and selected grant, opened the official opportunity notice, and confirm the applicant appears to meet its eligibility requirements. I agree to the <a href="/terms" target="_blank">Terms</a>, authorize GrantForgeUSA to begin the customized drafting service immediately after payment, and understand the $49.99 service is final and non-refundable once generation begins except where required by law or if GrantForgeUSA fails to deliver the purchased service. GrantForgeUSA screening is preliminary and funding is not guaranteed.
                          </span>
                        </label>

                        {checkoutError && <div className="status-message error" role="alert">{checkoutError}</div>}
                        <button className="button primary full-width checkout-button" type="button" onClick={beginCheckout} disabled={checkingOut || previewing}>
                          {checkingOut ? "Opening secure checkout…" : `Purchase full draft · ${serviceFee}`}
                        </button>
                        <p className="checkout-fine-print">Secure card checkout. GrantForgeUSA does not guarantee funding or agency approval.</p>
                      </>
                    ) : (
                      <div className="empty-preview">
                        <h3>Select a grant to preview.</h3>
                        <p>Your short proposal preview and checkout decision will appear here.</p>
                      </div>
                    )}
                  </aside>
                </div>
              )}
            </div>
          </section>
        )}

        <section className="section final-cta">
          <div className="shell final-cta-inner">
            <div>
              <span className="eyebrow">GrantForgeUSA</span>
              <h2>Start with the match, not the blank page.</h2>
              <p>Search and preview first. Purchase the full draft only after you see an opportunity you want to pursue.</p>
            </div>
            <a className="button primary" href="#start">Find my grants</a>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/thanks") return <ThankYouPage />;
  if (LEGAL_PAGES[path]) return <LegalPage page={LEGAL_PAGES[path]} />;
  return <LandingPage />;
}
