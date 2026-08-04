(function () {
  const EVIDENCE_THEME = {
    production_ready: {
      label: "Production ready",
      description: "Diagnostics found no material evidence-quality limitation.",
      className: "evidence-status evidence-status--ready",
    },
    analyst_review: {
      label: "Analyst review",
      description: "Usable for analysis after review of the recorded diagnostics.",
      className: "evidence-status evidence-status--review",
    },
    exploratory_only: {
      label: "Exploratory only",
      description: "Placeholder inputs or consistency gaps prevent policy-grade interpretation.",
      className: "evidence-status evidence-status--exploratory",
    },
    not_evaluated: {
      label: "Not evaluated",
      description: "Evidence quality is available after a model completes.",
      className: "evidence-status evidence-status--pending",
    },
  };

  function normalizeEvidenceStatus(value) {
    const status = String(value || "").trim().toLowerCase();
    return EVIDENCE_THEME[status] ? status : "not_evaluated";
  }

  function evidenceFromSummary(summary) {
    const integrated = summary && typeof summary.integrated_results === "object"
      ? summary.integrated_results
      : {};
    const quality = integrated && typeof integrated.model_quality === "object"
      ? integrated.model_quality
      : {};
    const status = normalizeEvidenceStatus(quality.status);
    return {
      status,
      score: Number.isFinite(Number(quality.score)) ? Math.max(0, Math.min(100, Math.round(Number(quality.score)))) : 0,
      summary: String(quality.summary || ""),
      issueCount: Array.isArray(quality.issues) ? quality.issues.length : 0,
      requiresAcknowledgement: status === "exploratory_only",
    };
  }

  function evidenceFromModel(model, summary) {
    const fromSummary = evidenceFromSummary(summary || {});
    if (fromSummary.status !== "not_evaluated") return fromSummary;
    const status = normalizeEvidenceStatus(model && model.evidence_status);
    return {
      status,
      score: Number(model && model.evidence_score) || 0,
      summary: String((model && model.evidence_summary) || ""),
      issueCount: 0,
      requiresAcknowledgement: status === "exploratory_only",
    };
  }

  function EvidenceBadge({ status, summary = "", compact = false }) {
    const normalized = normalizeEvidenceStatus(status);
    if (normalized === "exploratory_only" || normalized === "not_evaluated") return null;
    const meta = EVIDENCE_THEME[normalized];
    const title = String(summary || meta.description);
    return (
      <span
        className={`${meta.className}${compact ? " is-compact" : ""}`}
        title={title}
        data-evidence-status={normalized}
      >
        <span className="evidence-status-dot" aria-hidden="true" />
        <span>{meta.label}</span>
      </span>
    );
  }

  function EvidenceNotice({ evidence, title = "Evidence status" }) {
    const resolved = evidence || evidenceFromSummary({});
    const status = normalizeEvidenceStatus(resolved.status);
    const meta = EVIDENCE_THEME[status];
    return (
      <section className={`evidence-notice evidence-notice--${status}`} aria-label={title}>
        <div>
          <div className="evidence-notice-eyebrow">{title}</div>
          <strong>{meta.label}</strong>
          <p>{resolved.summary || meta.description}</p>
        </div>
        {resolved.score ? <span className="evidence-score">{resolved.score}/100</span> : null}
      </section>
    );
  }

  window.EDIM_EVIDENCE = {
    EVIDENCE_THEME,
    normalizeEvidenceStatus,
    evidenceFromSummary,
    evidenceFromModel,
    EvidenceBadge,
    EvidenceNotice,
  };
})();
