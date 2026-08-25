(function () {
  const { useEffect, useMemo, useRef, useState } = React;

  const JOURNEY_STEPS = [
    {
      title: "Define the question",
      body: "Start with a concrete planning question: which investment pathway, policy package, or infrastructure option should be tested?",
    },
    {
      title: "Select the architecture",
      body: "Choose whether to run an energy-only analysis or the full Energy-Development architecture.",
    },
    {
      title: "Choose scenario pathways",
      body: "Select scenario options through model-owned scenario channels, such as energy pathway, target pathway, target year, or development linkage options.",
    },
    {
      title: "Review datasets",
      body: "Use default datasets or upload user-specific data. Runs snapshot the selected dataset versions at submission time.",
    },
    {
      title: "Run and monitor",
      body: "Submit the run, track status, and review progress events.",
    },
    {
      title: "Read results",
      body: "Explore outputs through result tabs, charts, artifacts, logs, and reports.",
    },
    {
      title: "Compare and communicate",
      body: "Compare runs within a project and export packages that preserve outputs, reports, and dataset references.",
    },
  ];

  const SCENARIO_CHANNELS = [
    ["Energy pathway", "What energy-system future is being tested?"],
    ["Target pathway", "What policy or transition target is being explored?"],
    ["Target year", "Which planning horizon should the run evaluate?"],
    ["Model engine", "Which energy model module is used where options exist?"],
    ["Development linkage", "How energy outputs connect to development analysis in the full architecture."],
  ];

  const ENERGY_OUTPUTS = [
    "Generation mix",
    "Installed capacity",
    "Transmission expansion",
    "System cost",
    "Investment needs",
    "Emissions",
    "Energy balance",
    "Technology deployment",
  ];

  const DEVELOPMENT_OUTPUTS = [
    "Sectoral effects",
    "Employment implications",
    "Economic value creation",
    "Productive-use opportunities",
    "Service delivery relevance",
    "Affordability considerations",
    "Fiscal or investment implications",
    "Development co-benefits",
  ];

  const INTERPRETATION_PRINCIPLES = [
    "Compare scenarios, do not overread a single run.",
    "Check assumptions before interpreting outputs.",
    "Look for trade-offs and co-benefits together.",
    "Treat uncertainty as part of the planning process.",
    "Use exports and reports to support dialogue, not replace judgment.",
  ];

  const COUNTRY_WORKFLOW = [
    "Create a project for a country, sector, or planning question.",
    "Define a first baseline or reference run.",
    "Duplicate the run and adjust scenario assumptions.",
    "Compare results across runs.",
    "Review assumptions, artifacts, and reports.",
    "Export a project package for discussion.",
    "Refine the next scenario based on stakeholder feedback.",
  ];

  function usePrefersReducedMotion() {
    const [reduced, setReduced] = useState(false);
    useEffect(() => {
      if (!window.matchMedia) return undefined;
      const query = window.matchMedia("(prefers-reduced-motion: reduce)");
      setReduced(Boolean(query.matches));
      const onChange = () => setReduced(Boolean(query.matches));
      if (query.addEventListener) query.addEventListener("change", onChange);
      else query.addListener(onChange);
      return () => {
        if (query.removeEventListener) query.removeEventListener("change", onChange);
        else query.removeListener(onChange);
      };
    }, []);
    return reduced;
  }

  function useScrollSteps(length) {
    const [activeStep, setActiveStep] = useState(0);
    const reducedMotion = usePrefersReducedMotion();
    const elementsRef = useRef([]);

    useEffect(() => {
      if (reducedMotion || typeof IntersectionObserver === "undefined") return undefined;
      const observer = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
          if (!visible || !visible.target) return;
          const index = Number(visible.target.getAttribute("data-methodology-step"));
          if (Number.isFinite(index)) setActiveStep(index);
        },
        { root: null, threshold: [0.25, 0.45, 0.65], rootMargin: "-18% 0px -28% 0px" }
      );
      elementsRef.current.slice(0, length).forEach((element) => {
        if (element) observer.observe(element);
      });
      return () => observer.disconnect();
    }, [length, reducedMotion]);

    function setStepRef(index) {
      return (element) => {
        elementsRef.current[index] = element;
      };
    }

    return { activeStep, setStepRef, setActiveStep };
  }

  function HeroBackground() {
    const ref = useRef(null);
    const reducedMotion = usePrefersReducedMotion();

    function onPointerMove(event) {
      if (reducedMotion || !ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 100;
      const y = ((event.clientY - rect.top) / Math.max(1, rect.height)) * 100;
      ref.current.style.setProperty("--methodology-hero-x", `${x}%`);
      ref.current.style.setProperty("--methodology-hero-y", `${y}%`);
    }

    return (
      <div ref={ref} className="methodology-hero-visual" onPointerMove={onPointerMove} aria-hidden="true">
        <svg viewBox="0 0 1200 720" preserveAspectRatio="none">
          <defs>
            <linearGradient id="methodologyHeroLine" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#60a5fa" stopOpacity="0.42" />
              <stop offset="0.55" stopColor="#22d3ee" stopOpacity="0.2" />
              <stop offset="1" stopColor="#fbbf24" stopOpacity="0.16" />
            </linearGradient>
          </defs>
          <path d="M0 432 C165 318 238 492 390 352 C532 221 638 345 776 238 C936 114 1028 250 1200 138" />
          <path d="M0 548 C180 444 276 578 440 468 C596 364 692 440 836 330 C982 219 1075 315 1200 238" />
          <path d="M40 170 C215 92 340 190 486 140 C645 84 760 152 914 98 C1046 53 1112 86 1200 64" />
          {Array.from({ length: 34 }).map((_, index) => {
            const x = 56 + ((index * 139) % 1088);
            const y = 72 + ((index * 83) % 560);
            const r = index % 7 === 0 ? 4.2 : 2.4;
            return <circle key={index} cx={x} cy={y} r={r} />;
          })}
        </svg>
      </div>
    );
  }

  function MethodologyConceptVisual({ title, description, variant = "network", activeIndex = 0 }) {
    const dots = useMemo(() => Array.from({ length: 18 }).map((_, index) => ({
      x: 18 + ((index * 37) % 70),
      y: 18 + ((index * 53) % 62),
      r: index % 5 === 0 ? 4 : 2.4,
    })), []);
    return (
      <div className={`methodology-placeholder methodology-placeholder-${variant}`}>
        <div className="methodology-placeholder-art" aria-hidden="true">
          <svg viewBox="0 0 320 220" preserveAspectRatio="none">
            {variant === "layers" ? (
              <>
                {[0, 1, 2, 3].map((row) => (
                  <path key={row} d={`M38 ${58 + row * 29} C88 ${31 + row * 26}, 142 ${84 + row * 13}, 190 ${52 + row * 27} C232 ${25 + row * 18}, 266 ${52 + row * 22}, 292 ${40 + row * 27}`} />
                ))}
                {[0, 1, 2, 3].map((row) => <rect key={`rect-${row}`} x={50 + row * 18} y={42 + row * 30} width="195" height="34" rx="12" />)}
              </>
            ) : variant === "report" ? (
              <>
                <rect x="52" y="28" width="215" height="164" rx="18" />
                <path d="M80 70 H228" />
                <path d="M80 96 H178" />
                <path d="M80 128 H238" />
                <rect x="78" y="142" width="42" height="26" rx="8" />
                <rect x="132" y="132" width="42" height="36" rx="8" />
                <rect x="186" y="116" width="42" height="52" rx="8" />
              </>
            ) : variant === "timeline" ? (
              <>
                <path d="M48 112 C96 62, 130 162, 174 106 C218 49, 244 132, 284 78" />
                {[0, 1, 2, 3, 4].map((row) => <circle key={row} cx={58 + row * 55} cy={row % 2 ? 130 : 86} r={12 + row} />)}
              </>
            ) : variant === "scenario" ? (
              <>
                {[0, 1, 2, 3, 4].map((row) => <rect key={row} x={32 + row * 55} y={62 + (row % 2) * 32} width="44" height="58" rx="14" />)}
                <path d="M76 91 H87 C103 91 103 124 120 124 H139" />
                <path d="M185 91 H195 C213 91 212 124 230 124 H250" />
              </>
            ) : variant === "map" ? (
              <>
                <path d="M30 142 C72 96, 98 122, 124 82 C170 10, 219 62, 282 44" />
                <path d="M40 172 C90 138, 132 171, 184 122 C221 88, 250 103, 294 84" />
                <path d="M64 54 L112 84 L108 136 L58 156 L24 118 Z" />
                <path d="M174 46 L238 74 L230 142 L172 164 L130 114 Z" />
              </>
            ) : (
              <>
                {dots.map((dot, index) => <circle key={index} cx={`${dot.x}%`} cy={`${dot.y}%`} r={dot.r + (index === activeIndex ? 2 : 0)} />)}
                {dots.slice(0, 12).map((dot, index) => {
                  const next = dots[(index * 3 + 5) % dots.length];
                  return <line key={`line-${index}`} x1={`${dot.x}%`} y1={`${dot.y}%`} x2={`${next.x}%`} y2={`${next.y}%`} />;
                })}
              </>
            )}
          </svg>
        </div>
        <div className="methodology-placeholder-caption">
          <div>{title}</div>
          <p>{description}</p>
        </div>
      </div>
    );
  }

  function InsightCards() {
    const cards = [
      ["Energy view", "Technologies, infrastructure, costs, emissions."],
      ["Development view", "Jobs, sectors, productivity, services, equity."],
      ["Integrated view", "Trade-offs, co-benefits, investment priorities."],
    ];
    return (
      <div className="methodology-insight-grid">
        {cards.map(([title, body], index) => (
          <article className="methodology-insight-card" key={title} style={{ transitionDelay: `${index * 80}ms` }}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    );
  }

  function StickyJourney() {
    const { activeStep, setStepRef } = useScrollSteps(JOURNEY_STEPS.length);
    return (
      <section className="methodology-section methodology-journey-section" id="methodology-journey">
        <div className="methodology-section-copy methodology-section-copy-narrow">
          <div className="methodology-eyebrow">Modeling journey</div>
          <h2>A scenario is built step by step</h2>
          <p>
            EDIM is organized around projects and model runs. A project represents a country, policy question, or investment
            planning process. Each model run captures a specific scenario configuration, dataset snapshot, model architecture,
            and set of assumptions. This makes it possible to compare alternatives while preserving the exact inputs used for
            each run.
          </p>
          <div className="methodology-scroll-steps">
            {JOURNEY_STEPS.map((step, index) => (
              <article
                key={step.title}
                ref={setStepRef(index)}
                data-methodology-step={index}
                className={`methodology-scroll-step ${activeStep === index ? "active" : ""}`}
              >
                <span>Step {index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </article>
            ))}
          </div>
        </div>
        <aside className="methodology-sticky-panel">
          <div className="methodology-flow-card">
            <div className="methodology-flow-progress" style={{ height: `${((activeStep + 1) / JOURNEY_STEPS.length) * 100}%` }} />
            {JOURNEY_STEPS.map((step, index) => (
              <div key={step.title} className={`methodology-flow-row ${activeStep === index ? "active" : activeStep > index ? "complete" : ""}`}>
                <span>{index + 1}</span>
                <div>{step.title}</div>
              </div>
            ))}
          </div>
        </aside>
      </section>
    );
  }

  function ArchitectureExplainer({ architectureCatalog }) {
    const [selectedArchitecture, setSelectedArchitecture] = useState("energy-development");
    const ArchitectureDiagram = window.EDIMMethodologyArchitectureDiagram;
    const modeCopy = selectedArchitecture === "energy-only"
      ? "Energy-only mode focuses on energy pathways, infrastructure choices, costs, generation, transmission, emissions, and energy-system outputs without running the development linkage."
      : "Energy-Development mode runs the full integrated workflow, connecting energy model outputs through bridge and MRIO analysis to broader outcomes such as sectoral activity, jobs, value creation, and development priorities.";
    return (
      <section className="methodology-section methodology-architecture-section" id="methodology-architecture">
        <div className="methodology-section-copy">
          <div className="methodology-eyebrow">Architecture modes</div>
          <h2>Two ways to run the system</h2>
          <p>
            EDIM can run different model architectures depending on the question. The architecture determines which parts of
            the modeling chain are activated and which result surfaces are shown.
          </p>
          <div className="methodology-segmented" role="group" aria-label="Select architecture explanation">
            <button
              type="button"
              className={selectedArchitecture === "energy-only" ? "active" : ""}
              onClick={() => setSelectedArchitecture("energy-only")}
            >
              Energy-only
            </button>
            <button
              type="button"
              className={selectedArchitecture === "energy-development" ? "active" : ""}
              onClick={() => setSelectedArchitecture("energy-development")}
            >
              Energy-Development
            </button>
          </div>
          <p className="methodology-mode-copy">{modeCopy}</p>
          <p className="methodology-microcopy">
            The selected architecture controls which stages are active, which outputs are generated, and which result tabs are visible.
          </p>
        </div>
        <div className="methodology-architecture-card">
          {ArchitectureDiagram ? (
            <ArchitectureDiagram selectedArchitecture={selectedArchitecture} architectureCatalog={architectureCatalog} activeNodeIds={selectedArchitecture === "energy-only" ? ["scenario", "adapter", "calliope_data", "calliope", "outputs"] : []} />
          ) : (
            <MethodologyConceptVisual
              variant="network"
              title="Model architecture flow"
              description="Scenario assumptions move through model stages and into comparable energy and development outputs."
            />
          )}
        </div>
      </section>
    );
  }

  function ScenarioChannelCards() {
    const { activeStep, setStepRef } = useScrollSteps(SCENARIO_CHANNELS.length);
    return (
      <section className="methodology-section methodology-scenario-section" id="methodology-scenarios">
        <div className="methodology-section-copy methodology-section-copy-wide">
          <div className="methodology-eyebrow">Scenario channels</div>
          <h2>Scenarios are assembled through channels</h2>
          <p>
            A scenario is not a single setting. It is a structured combination of choices owned by the model architecture.
            EDIM exposes those choices as scenario channels. These channels may represent pathway assumptions, target years,
            technology choices, energy model engines, or development linkage options depending on the selected architecture.
            The user does not need to understand internal model files. The platform presents the available channels, validates
            the selected configuration, and preserves the submitted scenario as part of the run record.
          </p>
        </div>
        <div className="methodology-channel-grid">
          {SCENARIO_CHANNELS.map(([title, body], index) => (
            <article
              key={title}
              ref={setStepRef(index)}
              data-methodology-step={index}
              className={`methodology-channel-card ${activeStep >= index ? "active" : ""}`}
              tabIndex="0"
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>
    );
  }

  function MetricChipGrid({ items }) {
    return (
      <div className="methodology-chip-grid">
        {items.map((item) => (
          <button key={item} type="button" className="methodology-chip" title={`Plain-language output: ${item}`}>
            {item}
          </button>
        ))}
      </div>
    );
  }

  function InterpretationPrinciples() {
    const [active, setActive] = useState(0);
    return (
      <section className="methodology-section methodology-interpretation-section" id="methodology-interpretation">
        <div className="methodology-section-copy">
          <div className="methodology-eyebrow">Interpretation</div>
          <h2>Results are decision evidence, not automatic decisions</h2>
          <p>
            EDIM results should be read as structured evidence for comparison. The platform helps users see how scenarios
            differ, where trade-offs emerge, and which assumptions drive outcomes. Results are most useful when paired with
            local knowledge, stakeholder input, financing realities, and policy priorities.
          </p>
          <div className="methodology-principle-list">
            {INTERPRETATION_PRINCIPLES.map((principle, index) => (
              <button
                type="button"
                key={principle}
                className={active === index ? "active" : ""}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onClick={() => setActive(index)}
              >
                <span>{index + 1}</span>
                {principle}
              </button>
            ))}
          </div>
        </div>
        <div className="methodology-report-mockup" aria-label="Report mockup with highlighted interpretation focus">
          <div className="methodology-report-header" />
          <div className={`methodology-report-band band-${active}`} />
          <div className="methodology-report-gridline" />
          <div className="methodology-report-cards">
            {[0, 1, 2].map((row) => <span key={row} className={active === row ? "active" : ""} />)}
          </div>
          <div className="methodology-report-chart">
            {[0, 1, 2, 3, 4].map((row) => <span key={row} style={{ height: `${24 + row * 12 + (active === row ? 16 : 0)}%` }} />)}
          </div>
          <div className="methodology-placeholder-caption compact">
            <div>Report interpretation map</div>
            <p>Principles highlight assumptions, comparison views, uncertainty, and communication outputs.</p>
          </div>
        </div>
      </section>
    );
  }

  function MethodologyPage({ onOpenProjects, onStartProject, onReturnDashboard, architectureCatalog, header }) {
    const openProjects = typeof onOpenProjects === "function" ? onOpenProjects : function () {};
    const returnDashboard = typeof onReturnDashboard === "function" ? onReturnDashboard : openProjects;

    return (
      <div className="methodology-shell">
        {header || null}
        <main>
          <section className="methodology-hero-section">
            <HeroBackground />
            <div className="methodology-hero-content">
              <div className="methodology-eyebrow">METHODOLOGY</div>
              <h1>From energy scenarios to development insight</h1>
              <p>
                EDIM helps users explore how energy choices can shape wider development pathways. It links energy system
                modeling with economic and development analysis so that scenarios can be compared not only by cost or emissions,
                but also by their implications for investment, productivity, jobs, services, affordability, and resilience.
              </p>
              <a className="methodology-scroll-cta" href="#methodology-integrated">Scroll to explore</a>
            </div>
          </section>

          <nav className="methodology-reading-nav" aria-label="Methodology sections">
            <a href="#methodology-integrated">Purpose</a>
            <a href="#methodology-journey">Workflow</a>
            <a href="#methodology-architecture">Architecture</a>
            <a href="#methodology-scenarios">Scenarios</a>
            <a href="#methodology-datasets">Data</a>
            <a href="#methodology-interpretation">Interpretation</a>
          </nav>

          <section className="methodology-section methodology-intro-section" id="methodology-integrated">
            <div className="methodology-section-copy">
              <div className="methodology-eyebrow">Why integrated modeling?</div>
              <h2>Energy decisions rarely stay inside the energy sector</h2>
              <p>
                A power-sector investment may change generation costs, but it can also affect jobs, fiscal pressure,
                productive sectors, service delivery, and household affordability. Traditional energy models are strong at
                representing technologies, infrastructure, costs, constraints, and emissions. Economic and development models
                are better suited to tracing effects across sectors, value chains, employment, and public priorities. EDIM
                brings these perspectives into one decision workflow so that users can configure scenarios, run model
                architectures, compare outcomes, and generate outputs that support planning, policy dialogue, and investment
                prioritization.
              </p>
              <InsightCards />
            </div>
            <MethodologyConceptVisual
              variant="network"
              title="Integrated decision map"
              description="Energy-system and development-system evidence align into one integrated decision map."
            />
          </section>

          <StickyJourney />
          <ArchitectureExplainer architectureCatalog={architectureCatalog} />
          <ScenarioChannelCards />

          <section className="methodology-section methodology-datasets-section" id="methodology-datasets">
            <div className="methodology-section-copy">
              <div className="methodology-eyebrow">Datasets and assumptions</div>
              <h2>Every run preserves its assumptions</h2>
              <p>
                Model results are only meaningful when the inputs are clear. EDIM allows users to work with default datasets
                or upload project-relevant data. When a run is submitted, the platform snapshots the exact active dataset
                versions used for that run. This means that results can be reviewed, exported, and compared later with a clear
                record of the assumptions behind them.
              </p>
              <ul className="methodology-clean-list">
                <li>Datasets are user-scoped and reusable across projects.</li>
                <li>Uploaded files can have immutable versions.</li>
                <li>Submitted runs preserve the exact dataset versions used.</li>
                <li>Exports include the references needed to interpret results.</li>
              </ul>
            </div>
            <MethodologyConceptVisual
              variant="layers"
              title="Dataset layers and run snapshot"
              description="Default data, uploaded data, active versions, and run snapshots stack into a preserved assumption record."
            />
          </section>

          <section className="methodology-section methodology-output-section">
            <div className="methodology-large-card">
              <div className="methodology-eyebrow">Energy model</div>
              <h2>The energy model tests the physical transition pathway</h2>
              <p>
                The energy model represents how an energy system can evolve under different constraints and assumptions. It
                helps users explore questions such as what infrastructure may be needed, how generation changes, how costs
                evolve, where transmission or investment bottlenecks may appear, and how emissions trajectories respond to
                different choices.
              </p>
              <MetricChipGrid items={ENERGY_OUTPUTS} />
            </div>
            <MethodologyConceptVisual
              variant="map"
              title="Energy system pathway"
              description="Generation nodes, transmission links, demand centers, and changing pathway lines."
            />
          </section>

          <section className="methodology-section methodology-output-section reverse">
            <MethodologyConceptVisual
              variant="network"
              title="Development sector network"
              description="Energy outputs connect into agriculture, industry, services, transport, health, education, and households."
            />
            <div className="methodology-large-card">
              <div className="methodology-eyebrow">Development model</div>
              <h2>The development model traces wider effects</h2>
              <p>
                In the full Energy-Development architecture, energy-system outputs are connected to development analysis. This
                helps users explore how changes in energy investment, costs, demand, or infrastructure may relate to wider
                economic and social outcomes. The goal is not to predict a single future with certainty, but to make trade-offs
                and co-benefits easier to compare.
              </p>
              <MetricChipGrid items={DEVELOPMENT_OUTPUTS} />
            </div>
          </section>

          <InterpretationPrinciples />

          <section className="methodology-section methodology-country-section">
            <div className="methodology-section-copy">
              <div className="methodology-eyebrow">Country workflow</div>
              <h2>A workflow for policy and investment dialogue</h2>
              <p>
                A typical EDIM workflow begins with a country question and ends with a structured comparison of options. A user
                may create a project for a national planning process, configure several model runs, compare outputs, generate
                reports, and export packages for technical review or partner discussions.
              </p>
              <ol className="methodology-timeline-list">
                {COUNTRY_WORKFLOW.map((item, index) => (
                  <li key={item}><span>{index + 1}</span>{item}</li>
                ))}
              </ol>
            </div>
            <MethodologyConceptVisual
              variant="timeline"
              title="Country-office planning pathway"
              description="Scenario cards move from question to comparison to report package."
            />
          </section>

          <section className="methodology-closing-section">
            <MethodologyConceptVisual
              variant="scenario"
              title="Integrated decision workflow"
              description="Energy pathway, development outcomes, and report package connected into one decision workflow."
            />
            <div>
              <div className="methodology-eyebrow">Next step</div>
              <h2>Build a scenario. Compare the pathway. Understand the implications.</h2>
              <p>
                The methodology is designed to make complex model systems usable for practical decision-making. EDIM keeps the
                modeling workflow structured: projects organize the question, runs preserve the assumptions, architectures define
                the modeling pathway, and outputs support comparison, reporting, and dialogue.
              </p>
              <div className="methodology-closing-actions">
                <button type="button" onClick={openProjects}>Open projects</button>
                <button type="button" onClick={returnDashboard}>Return to dashboard</button>
              </div>
            </div>
          </section>
        </main>
      </div>
    );
  }

  window.EDIMMethodology = {
    MethodologyPage,
    useScrollSteps,
    MethodologyConceptVisual,
  };
})();
