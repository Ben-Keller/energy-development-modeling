const {
  useEffect: useReactEffect,
  useMemo: useReactMemo,
  useRef: useReactRef,
  useState: useReactState,
} = React;

const EDIM_HERO_MODULES = [
  { id: "scenario", label: "Scenario Controls", x: 0.16, y: 0.24, w: 0.18, h: 0.1, depth: 0.7, warmth: 0.2 },
  { id: "data", label: "Data Inputs", x: 0.38, y: 0.16, w: 0.17, h: 0.11, depth: 0.46, warmth: 0.12 },
  { id: "energy", label: "Energy Model", x: 0.62, y: 0.26, w: 0.18, h: 0.12, depth: 0.82, warmth: 0.18 },
  { id: "bridge", label: "Bridge Layer", x: 0.48, y: 0.45, w: 0.15, h: 0.09, depth: 0.62, warmth: 0.72 },
  { id: "economy", label: "Economic Model", x: 0.72, y: 0.52, w: 0.19, h: 0.12, depth: 0.58, warmth: 0.36 },
  { id: "runs", label: "Model Runs", x: 0.22, y: 0.58, w: 0.17, h: 0.1, depth: 0.5, warmth: 0.42 },
  { id: "artifacts", label: "Output Artifacts", x: 0.42, y: 0.74, w: 0.18, h: 0.1, depth: 0.72, warmth: 0.9 },
  { id: "dashboard", label: "Decision Dashboard", x: 0.68, y: 0.78, w: 0.21, h: 0.11, depth: 0.86, warmth: 0.62 },
];

const EDIM_HERO_PATHS = [
  { id: "scenario-data", from: "scenario", to: "data", pulse: true, strength: 0.62 },
  { id: "data-energy", from: "data", to: "energy", pulse: true, strength: 0.84 },
  { id: "scenario-runs", from: "scenario", to: "runs", pulse: false, strength: 0.42 },
  { id: "energy-bridge", from: "energy", to: "bridge", pulse: true, strength: 0.88 },
  { id: "bridge-economy", from: "bridge", to: "economy", pulse: true, strength: 0.78 },
  { id: "runs-artifacts", from: "runs", to: "artifacts", pulse: true, strength: 0.58 },
  { id: "energy-artifacts", from: "energy", to: "artifacts", pulse: false, strength: 0.5 },
  { id: "economy-dashboard", from: "economy", to: "dashboard", pulse: true, strength: 0.72 },
  { id: "artifacts-dashboard", from: "artifacts", to: "dashboard", pulse: true, strength: 0.86 },
  { id: "data-bridge", from: "data", to: "bridge", pulse: false, strength: 0.36 },
];

const EDIM_HERO_PALETTES = {
  solar: {
    background: "#140d05",
    primary: "#f59e0b",
    secondary: "#fb7185",
    tertiary: "#38bdf8",
    accent: "#fde047",
    label: "#fff7ed",
    soft: "#fed7aa",
    surface: "#25120a",
  },
  undp: {
    background: "#050b16",
    primary: "#2563eb",
    secondary: "#0ea5e9",
    tertiary: "#14b8a6",
    accent: "#f59e0b",
    label: "#dbeafe",
    soft: "#bfdbfe",
    surface: "#0f172a",
  },
};

const EDIM_HERO_THUMBNAIL_COUNT = 323;
const EDIM_NEUTRAL_POINTER = { active: false, x: 0.5, y: 0.5 };

function edimClamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function edimHexToRgb(color) {
  const clean = String(color || "").replace("#", "");
  if (clean.length !== 6) return [255, 255, 255];
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function edimAlpha(color, opacity) {
  const [r, g, b] = edimHexToRgb(color);
  return `rgba(${r}, ${g}, ${b}, ${edimClamp(opacity, 0, 1).toFixed(4)})`;
}

function edimPalette(theme) {
  return EDIM_HERO_PALETTES[theme] || EDIM_HERO_PALETTES.solar;
}

function edimTuning(tuning, key, fallback, min = 0, max = 3) {
  const value = Number(tuning && tuning[key]);
  if (!Number.isFinite(value)) return fallback;
  return edimClamp(value, min, max);
}

function edimInterpolateColor(colors, value) {
  const safe = edimClamp(value, 0, 1);
  const position = safe * (colors.length - 1);
  const startIndex = Math.floor(position);
  const endIndex = Math.min(colors.length - 1, startIndex + 1);
  const mix = position - startIndex;
  const start = edimHexToRgb(colors[startIndex]);
  const end = edimHexToRgb(colors[endIndex]);
  const channels = start.map((channel, index) => Math.round(channel + (end[index] - channel) * mix));
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}

function edimHashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function edimWebpBasePath() {
  const configured = String(window.EDIM_HERO_WEBP_BASE || "").trim();
  return (configured || "./assets/webp").replace(/\/+$/, "");
}

function edimThumbnailUrl(module, seed) {
  const index = (edimHashString(`${seed}:${module.id}:${module.label}`) % EDIM_HERO_THUMBNAIL_COUNT) + 1;
  return `${edimWebpBasePath()}/photo-${String(index).padStart(3, "0")}.webp`;
}

function edimUseElementSize() {
  const ref = useReactRef(null);
  const [size, setSize] = useReactState({ width: 0, height: 0 });

  useReactEffect(() => {
    const element = ref.current;
    if (!element) return undefined;

    function publishSize() {
      const rect = element.getBoundingClientRect();
      const next = {
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
      setSize((current) => current.width === next.width && current.height === next.height ? current : next);
    }

    publishSize();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", publishSize);
      return () => window.removeEventListener("resize", publishSize);
    }

    const observer = new ResizeObserver(publishSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, size };
}

function edimUsePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useReactState(false);

  useReactEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(query.matches);

    function handleChange(event) {
      setReducedMotion(event.matches);
    }

    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", handleChange);
      return () => query.removeEventListener("change", handleChange);
    }
    query.addListener(handleChange);
    return () => query.removeListener(handleChange);
  }, []);

  return reducedMotion;
}

function edimModuleInfluence(module, pointer, width, height, interaction, activity) {
  if (!pointer.active || activity <= 0.001) return 0;
  const distance = Math.hypot(module.centerX - pointer.x * width, module.centerY - pointer.y * height);
  const radius = Math.min(width, height) * 0.46 * interaction;
  if (distance > radius) return 0;
  return Math.pow(1 - distance / radius, 0.68) * activity;
}

function edimRenderModules(width, height, pointer, moduleScale, interaction, seed, activity) {
  return EDIM_HERO_MODULES.map((module) => {
    const moduleWidth = module.w * width * moduleScale;
    const moduleHeight = module.h * height * moduleScale;
    const left = module.x * width - moduleWidth / 2;
    const top = module.y * height - moduleHeight / 2;
    const centerX = left + moduleWidth / 2;
    const centerY = top + moduleHeight / 2;
    const influence = edimModuleInfluence({ centerX, centerY }, pointer, width, height, interaction, activity);
    return {
      ...module,
      left,
      top,
      width: moduleWidth,
      height: moduleHeight,
      centerX,
      centerY,
      influence,
      gravityX: 0,
      gravityY: 0,
      thumbnailHref: edimThumbnailUrl(module, seed),
    };
  });
}

function edimPathD(from, to, time, index, driftStrength, curvature) {
  const midX = (from.centerX + to.centerX) / 2;
  const midY = (from.centerY + to.centerY) / 2;
  const dx = to.centerX - from.centerX;
  const dy = to.centerY - from.centerY;
  const normalLength = Math.max(1, Math.hypot(dx, dy));
  const normalX = -dy / normalLength;
  const normalY = dx / normalLength;
  const curve = (18 + (index % 4) * 9) * (index % 2 ? 1 : -1) * curvature;
  const drift = Math.sin(time * 0.001 + index * 1.7) * 5 * driftStrength;
  const controlX = midX + normalX * (curve + drift);
  const controlY = midY + normalY * (curve + drift);
  return `M ${from.centerX.toFixed(1)} ${from.centerY.toFixed(1)} Q ${controlX.toFixed(1)} ${controlY.toFixed(1)} ${to.centerX.toFixed(1)} ${to.centerY.toFixed(1)}`;
}

function EdimHeroArchitectureSvg({ width, height, seed, pointer, pointerRef, reducedMotion, tuning, colors, interactive }) {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const moduleScale = edimTuning(tuning, "scale", 1, 0.5, 1.8);
  const driftStrength = edimTuning(tuning, "drift", 1, 0, 2.5);
  const curvature = edimTuning(tuning, "curvature", 1, 0, 8);
  const interaction = edimTuning(tuning, "interaction", 1, 0.1, 2.5);
  const lineStrength = edimTuning(tuning, "lines", 1, 0, 4);
  const labelStrength = edimTuning(tuning, "labels", 1, 0, 2.5);
  const titleStrength = edimTuning(tuning, "titleStrength", 1.35, 0, 3);
  const pulseStrength = edimTuning(tuning, "pulses", 1, 0, 2);
  const pulseSpeed = edimTuning(tuning, "pulseSpeed", 1, 0.2, 3);
  const glowStrength = edimTuning(tuning, "glow", 1, 0, 2.5);
  const flashlightStrength = edimTuning(tuning, "flashlight", 1.35, 0, 3);
  const flashlightSize = edimTuning(tuning, "flashlightSize", 1, 0.35, 2.5);
  const imageStrength = edimTuning(tuning, "images", 1, 0, 2);
  const contrast = edimTuning(tuning, "contrast", 1, 0.2, 2.5);
  const sceneRef = useReactRef(null);
  const cursorGradientRef = useReactRef(null);
  const cursorGlowRef = useReactRef(null);
  const pulseGroupRef = useReactRef(null);
  const moduleRefs = useReactRef({});
  const pathRefs = useReactRef({});
  const safeId = useReactMemo(() => `edim-hero-${Math.random().toString(36).slice(2)}`, []);
  const colorRamp = useReactMemo(() => [colors.primary, colors.secondary, colors.tertiary, colors.accent], [colors]);
  const modules = useReactMemo(
    () => edimRenderModules(safeWidth, safeHeight, EDIM_NEUTRAL_POINTER, moduleScale, interaction, seed, 0),
    [interaction, moduleScale, safeHeight, safeWidth, seed],
  );
  const moduleMap = useReactMemo(() => new Map(modules.map((module) => [module.id, module])), [modules]);
  const renderedPaths = useReactMemo(() => EDIM_HERO_PATHS.map((path, index) => {
    const from = moduleMap.get(path.from);
    const to = moduleMap.get(path.to);
    if (!from || !to) return null;
    return {
      ...path,
      d: edimPathD(from, to, seed * 41, index, driftStrength, curvature),
      influence: 0,
    };
  }).filter(Boolean), [curvature, driftStrength, moduleMap, seed]);

  useReactEffect(() => {
    const scene = sceneRef.current;
    const cursorGradient = cursorGradientRef.current;
    const cursorGlow = cursorGlowRef.current;
    if (!scene || !cursorGradient || !cursorGlow) return undefined;

    const moduleDom = modules.map((module) => {
      const group = moduleRefs.current[module.id];
      const query = (role) => group && group.querySelector(`[data-role="${role}"]`);
      return {
        module,
        refs: {
          group,
          glow: query("module-glow"),
          base: query("module-base"),
          image: query("module-image"),
          shell: query("module-shell"),
          glass: query("module-glass"),
          inner: query("module-inner"),
          topBar: query("module-top-bar"),
          label: query("module-label"),
        },
      };
    });
    const pathDom = renderedPaths.map((path, index) => ({ path, index, element: pathRefs.current[path.id] }));
    const pulseGroup = pulseGroupRef.current;
    const smoothed = { x: 0.5, y: 0.5, activity: 0 };
    let frameId = 0;
    let previousTime = performance.now();

    function updateStatic() {
      scene.setAttribute("transform", "");
      cursorGradient.setAttribute("cx", "50%");
      cursorGradient.setAttribute("cy", "50%");
      cursorGradient.setAttribute("r", `${(38 + flashlightSize * 15).toFixed(1)}%`);
      cursorGlow.setAttribute("opacity", String(Math.min(0.24, 0.04 * glowStrength * flashlightStrength)));
      moduleDom.forEach(({ refs }) => refs.group && refs.group.setAttribute("transform", ""));
      pathDom.forEach(({ path, element }) => {
        if (!element) return;
        element.setAttribute("d", path.d);
        element.setAttribute("stroke-width", String(0.72 + path.strength * 0.72));
        element.setAttribute("stroke-opacity", String((0.2 + path.strength * 0.18) * lineStrength));
      });
      if (pulseGroup) pulseGroup.setAttribute("opacity", String(0.68 * pulseStrength));
    }

    if (reducedMotion) {
      updateStatic();
      return undefined;
    }

    function tick(now) {
      const delta = edimClamp(now - previousTime, 8, 64);
      previousTime = now;
      const pointerSource = (pointerRef && pointerRef.current) || pointer;
      const targetActive = interactive && pointerSource.active;
      const targetX = targetActive ? pointerSource.x : 0.5;
      const targetY = targetActive ? pointerSource.y : 0.5;
      if (targetActive) {
        smoothed.x = targetX;
        smoothed.y = targetY;
      } else {
        const returnFollow = 1 - Math.pow(0.78, delta / 16.67);
        smoothed.x += (targetX - smoothed.x) * returnFollow;
        smoothed.y += (targetY - smoothed.y) * returnFollow;
      }
      const activityFollow = targetActive
        ? 1 - Math.pow(0.02, delta / 16.67)
        : 1 - Math.pow(0.74, delta / 16.67);
      smoothed.activity += ((targetActive ? 1 : 0) - smoothed.activity) * activityFollow;

      const pointerState = {
        active: smoothed.activity > 0.001,
        x: smoothed.x,
        y: smoothed.y,
      };
      const sceneActivity = smoothed.activity;
      const pointerX = pointerState.active ? pointerState.x : 0.5;
      const pointerY = pointerState.active ? pointerState.y : 0.5;
      const sceneShiftX = (pointerX - 0.5) * Math.min(34, safeWidth * 0.032) * interaction * sceneActivity;
      const sceneShiftY = (pointerY - 0.5) * Math.min(24, safeHeight * 0.032) * interaction * sceneActivity;
      const sceneScale = 1 + 0.007 * Math.min(1.5, interaction) * sceneActivity;
      scene.setAttribute("transform", `translate(${sceneShiftX.toFixed(2)} ${sceneShiftY.toFixed(2)}) translate(${(safeWidth / 2).toFixed(1)} ${(safeHeight / 2).toFixed(1)}) scale(${sceneScale.toFixed(4)}) translate(${(-safeWidth / 2).toFixed(1)} ${(-safeHeight / 2).toFixed(1)})`);
      const sceneGlow = Math.min(1, interaction * 0.72) * sceneActivity;
      cursorGradient.setAttribute("cx", `${(pointerX * 100).toFixed(1)}%`);
      cursorGradient.setAttribute("cy", `${(pointerY * 100).toFixed(1)}%`);
      cursorGradient.setAttribute("r", `${(38 + flashlightSize * 15).toFixed(1)}%`);
      cursorGlow.setAttribute("opacity", String(Math.min(0.98, (0.04 + sceneGlow * 0.94 * flashlightStrength) * glowStrength)));

      const runtimeModules = new Map();
      moduleDom.forEach(({ module, refs }) => {
        const influence = edimModuleInfluence(module, pointerState, safeWidth, safeHeight, interaction, sceneActivity);
        const rawGravityX = (pointerX * safeWidth - module.centerX) * 0.032 * influence * interaction;
        const rawGravityY = (pointerY * safeHeight - module.centerY) * 0.032 * influence * interaction;
        const gravityX = pointerState.active ? edimClamp(rawGravityX, -16, 16) : 0;
        const gravityY = pointerState.active ? edimClamp(rawGravityY, -12, 12) : 0;
        if (refs.group) refs.group.setAttribute("transform", `translate(${gravityX.toFixed(2)} ${gravityY.toFixed(2)})`);
        if (refs.glow) refs.glow.setAttribute("opacity", String((0.08 + influence * 0.26) * glowStrength));
        if (refs.base) refs.base.setAttribute("fill-opacity", String(0.16 + module.depth * 0.05 + influence * 0.025));
        if (refs.image) refs.image.setAttribute("opacity", String(Math.min(0.9, (0.56 + module.depth * 0.12 + influence * 0.16) * Math.min(1.12, contrast) * imageStrength)));
        if (refs.shell) {
          refs.shell.setAttribute("fill-opacity", String(Math.min(0.22, (0.08 + module.depth * 0.025 + influence * 0.045) * contrast)));
          refs.shell.setAttribute("stroke-opacity", String(Math.min(0.92, (0.52 + module.depth * 0.16 + influence * 0.38) * contrast)));
          refs.shell.setAttribute("stroke-width", String(1 + influence * 1.15));
        }
        if (refs.glass) {
          refs.glass.setAttribute("fill-opacity", String(0.16 + influence * 0.08));
          refs.glass.setAttribute("stroke-opacity", String((0.22 + influence * 0.34) * contrast));
          refs.glass.setAttribute("stroke-width", String(0.65 + influence * 0.45));
        }
        if (refs.inner) {
          refs.inner.setAttribute("stroke-opacity", String(0.18 + influence * 0.42));
          refs.inner.setAttribute("stroke-width", String(0.5 + influence * 0.5));
        }
        if (refs.topBar) refs.topBar.setAttribute("opacity", String((0.28 + influence * 0.34) * contrast));
        if (refs.label) refs.label.setAttribute("opacity", String(Math.min(1, (0.78 + influence * 0.22) * titleStrength * labelStrength)));
        runtimeModules.set(module.id, {
          ...module,
          influence,
          gravityX,
          gravityY,
          centerX: module.centerX + gravityX,
          centerY: module.centerY + gravityY,
        });
      });

      pathDom.forEach(({ path, index, element }) => {
        if (!element) return;
        const from = runtimeModules.get(path.from);
        const to = runtimeModules.get(path.to);
        if (!from || !to) return;
        const d = edimPathD(from, to, now + seed * 41, index, driftStrength, curvature);
        element.setAttribute("d", d);
        element.setAttribute("stroke-width", String(0.72 + path.strength * 0.72 + sceneGlow * 0.28));
        element.setAttribute("stroke-opacity", String((0.2 + path.strength * 0.18 + sceneGlow * 0.12) * lineStrength));
      });
      if (pulseGroup) pulseGroup.setAttribute("opacity", String((0.68 + sceneGlow * 0.18) * pulseStrength));

      frameId = window.requestAnimationFrame(tick);
    }

    frameId = window.requestAnimationFrame(tick);
    return () => {
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, [
    colors,
    contrast,
    curvature,
    driftStrength,
    flashlightSize,
    flashlightStrength,
    glowStrength,
    interactive,
    interaction,
    imageStrength,
    labelStrength,
    lineStrength,
    modules,
    pointer,
    pointerRef,
    pulseStrength,
    reducedMotion,
    renderedPaths,
    safeHeight,
    safeWidth,
    seed,
    titleStrength,
  ]);

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${safeWidth} ${safeHeight}`} preserveAspectRatio="xMidYMid slice" style={{ display: "block", pointerEvents: "none" }}>
      <defs>
        <radialGradient id={`${safeId}-ambient`} cx="50%" cy="48%" r="72%">
          <stop offset="0%" stopColor={edimAlpha(colors.primary, 0.15)} />
          <stop offset="48%" stopColor={edimAlpha(colors.secondary, 0.05)} />
          <stop offset="100%" stopColor={edimAlpha(colors.background, 0)} />
        </radialGradient>
        <linearGradient id={`${safeId}-glass`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={edimAlpha(colors.label, 0.13)} />
          <stop offset="52%" stopColor={edimAlpha(colors.secondary, 0.045)} />
          <stop offset="100%" stopColor={edimAlpha(colors.surface, 0.12)} />
        </linearGradient>
        <radialGradient ref={cursorGradientRef} id={`${safeId}-cursor-light`} cx="50%" cy="50%" r={`${(38 + flashlightSize * 15).toFixed(1)}%`}>
          <stop offset="0%" stopColor={edimAlpha(colors.secondary, 0.42)} />
          <stop offset="34%" stopColor={edimAlpha(colors.primary, 0.2)} />
          <stop offset="64%" stopColor={edimAlpha(colors.tertiary, 0.07)} />
          <stop offset="100%" stopColor={edimAlpha(colors.background, 0)} />
        </radialGradient>
      </defs>

      <rect width={safeWidth} height={safeHeight} fill="transparent" />
      <rect width={safeWidth} height={safeHeight} fill={`url(#${safeId}-ambient)`} opacity={0.8 * glowStrength} />
      <rect ref={cursorGlowRef} width={safeWidth} height={safeHeight} fill={`url(#${safeId}-cursor-light)`} opacity={Math.min(0.24, 0.04 * glowStrength * flashlightStrength)} />

      <g ref={sceneRef}>
        <g>
          {renderedPaths.map((path) => (
            <path
              key={path.id}
              id={`${safeId}-wire-${path.id}`}
              ref={(element) => {
                pathRefs.current[path.id] = element;
              }}
              d={path.d}
              fill="none"
              stroke={path.strength > 0.72 ? edimAlpha(colors.secondary, 0.5) : edimAlpha(colors.primary, 0.34)}
              strokeWidth={0.72 + path.strength * 0.72 + path.influence * 0.28}
              strokeOpacity={(0.2 + path.strength * 0.18 + path.influence * 0.12) * lineStrength}
              strokeLinecap="round"
            />
          ))}
        </g>

        {!reducedMotion && pulseStrength > 0 ? (
          <g ref={pulseGroupRef} opacity={0.68 * pulseStrength}>
            {renderedPaths.filter((path) => path.pulse).map((path, index) => {
              const speed = Math.max(2.8, 6.2) / pulseSpeed;
              const wireHref = `#${safeId}-wire-${path.id}`;
              const pulseHeight = 3.8 + path.strength * 1.4 + (index % 3) * 0.34;
              const pulseWidth = pulseHeight * 3.3;
              return (
                <g key={`pulse-${path.id}`}>
                  <rect
                    x={-pulseWidth * 0.62}
                    y={-pulseHeight * 0.95}
                    width={pulseWidth * 1.24}
                    height={pulseHeight * 1.9}
                    rx={pulseHeight * 0.95}
                    fill={index % 4 === 0 ? colors.accent : colors.secondary}
                    opacity={0.13}
                  >
                    <animateMotion dur={`${speed}s`} begin={`${index * 0.35}s`} repeatCount="indefinite" rotate="auto">
                      <mpath href={wireHref} xlinkHref={wireHref} />
                    </animateMotion>
                  </rect>
                  <rect
                    x={-pulseWidth / 2}
                    y={-pulseHeight / 2}
                    width={pulseWidth}
                    height={pulseHeight}
                    rx={pulseHeight / 2}
                    fill={index % 4 === 0 ? colors.accent : colors.secondary}
                    opacity={0.64}
                  >
                    <animateMotion dur={`${speed}s`} begin={`${index * 0.35}s`} repeatCount="indefinite" rotate="auto">
                      <mpath href={wireHref} xlinkHref={wireHref} />
                    </animateMotion>
                  </rect>
                </g>
              );
            })}
          </g>
        ) : null}

        <g>
          {modules.map((module) => {
            const fillOpacity = Math.min(0.22, (0.08 + module.depth * 0.025 + module.influence * 0.045) * contrast);
            const strokeOpacity = Math.min(0.92, (0.52 + module.depth * 0.16 + module.influence * 0.38) * contrast);
            const color = edimInterpolateColor(colorRamp, (module.warmth + module.depth * 0.23) % 1);
            const secondaryColor = edimInterpolateColor(colorRamp, (module.warmth + 0.34) % 1);
            const imageOpacity = Math.min(0.9, (0.56 + module.depth * 0.12 + module.influence * 0.16) * Math.min(1.12, contrast) * imageStrength);
            const clipId = `${safeId}-${module.id}-clip`;
            return (
              <g
                key={module.id}
                ref={(element) => {
                  moduleRefs.current[module.id] = element;
                }}
              >
                <clipPath id={clipId}>
                  <rect x={module.left} y={module.top} width={module.width} height={module.height} rx={18} />
                </clipPath>
                <rect data-role="module-glow" x={module.left - 8} y={module.top - 8} width={module.width + 16} height={module.height + 16} rx={24} fill={color} opacity={(0.08 + module.influence * 0.26) * glowStrength} />
                <rect data-role="module-base" x={module.left} y={module.top} width={module.width} height={module.height} rx={18} fill={color} fillOpacity={0.16 + module.depth * 0.05} />
                <image data-role="module-image" href={module.thumbnailHref} x={module.left} y={module.top} width={module.width} height={module.height} preserveAspectRatio="xMidYMid slice" clipPath={`url(#${clipId})`} opacity={imageOpacity} />
                <rect data-role="module-shell" x={module.left} y={module.top} width={module.width} height={module.height} rx={18} fill={color} fillOpacity={fillOpacity} stroke={color} strokeOpacity={strokeOpacity} strokeWidth={1 + module.influence * 1.15} />
                <rect data-role="module-glass" x={module.left} y={module.top} width={module.width} height={module.height} rx={18} fill={`url(#${safeId}-glass)`} fillOpacity={0.16 + module.influence * 0.08} stroke={secondaryColor} strokeOpacity={(0.22 + module.influence * 0.34) * contrast} strokeWidth={0.65 + module.influence * 0.45} />
                <rect data-role="module-inner" x={module.left + 2} y={module.top + 2} width={Math.max(0, module.width - 4)} height={Math.max(0, module.height - 4)} rx={16} fill="none" stroke="#ffffff" strokeOpacity={0.18 + module.influence * 0.42} strokeWidth={0.5 + module.influence * 0.5} />
                <rect data-role="module-top-bar" x={module.left + 8} y={module.top + 8} width={Math.max(8, module.width * 0.42)} height={1.6} rx={1} fill={secondaryColor} opacity={(0.28 + module.influence * 0.34) * contrast} />
                <text data-role="module-label" x={module.centerX} y={module.centerY + 4} fill={colors.label} textAnchor="middle" fontSize={module.label.length > 15 ? 9.5 : 10.5} fontWeight={800} letterSpacing="0.035em" opacity={Math.min(1, (0.78 + module.influence * 0.22) * titleStrength * labelStrength)} style={{ pointerEvents: "none", userSelect: "none" }}>
                  {module.label}
                </text>
              </g>
            );
          })}
        </g>
      </g>
    </svg>
  );
}

function HeroBackground({
  theme = "solar",
  intensity = 1,
  interactive = true,
  seed = 31,
  className = "",
  style,
  ariaHidden = true,
  tuning = {},
}) {
  const { ref, size } = edimUseElementSize();
  const reducedMotion = edimUsePrefersReducedMotion();
  const pointerRef = useReactRef(EDIM_NEUTRAL_POINTER);
  const width = size.width || 1440;
  const height = size.height || 760;
  const colors = useReactMemo(() => edimPalette(theme), [theme]);
  const safeIntensity = edimClamp(Number(intensity) || 1, 0.1, 2.5);

  useReactEffect(() => {
    if (!interactive || reducedMotion) {
      pointerRef.current = EDIM_NEUTRAL_POINTER;
      return undefined;
    }

    function handlePointerMove(event) {
      const element = ref.current;
      if (!element) return;
      const rect = element.getBoundingClientRect();
      if (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      ) {
        pointerRef.current = EDIM_NEUTRAL_POINTER;
        return;
      }
      pointerRef.current = {
        active: true,
        x: edimClamp((event.clientX - rect.left) / Math.max(rect.width, 1), 0, 1),
        y: edimClamp((event.clientY - rect.top) / Math.max(rect.height, 1), 0, 1),
      };
    }

    function clearPointer() {
      pointerRef.current = EDIM_NEUTRAL_POINTER;
    }

    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("pointerleave", clearPointer);
    window.addEventListener("blur", clearPointer);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", clearPointer);
      window.removeEventListener("blur", clearPointer);
      pointerRef.current = EDIM_NEUTRAL_POINTER;
    };
  }, [interactive, reducedMotion, ref]);

  return (
    <div
      ref={ref}
      className={`edim-hero-visual ${className}`.trim()}
      style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", ...(style || {}) }}
      aria-hidden={ariaHidden}
    >
      <EdimHeroArchitectureSvg
        width={width}
        height={height}
        reducedMotion={reducedMotion}
        pointer={pointerRef.current}
        pointerRef={pointerRef}
        colors={colors}
        seed={seed}
        intensity={safeIntensity}
        interactive={interactive}
        tuning={tuning}
      />
    </div>
  );
}

window.EDIMHeroBackground = { HeroBackground };
